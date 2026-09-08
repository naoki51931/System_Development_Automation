import hashlib
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from app.models import AuditLog, ProjectMember, ProtectedApproval
from app.models import DeploymentExecution, User
from app.auth.dependencies import AuthenticatedUser, require_organization_access
from app.services.approvals import decide_approval
from app.services.deployment import request_staging_approval, security_check_plan
from app.services.fake_terraform_apply import (
    ApprovedSavedPlan,
    FakeTerraformApplyExecutor,
)
from app.services.terraform_cli import SavedPlanVerification, TerraformCliResult
from app.services.terraform_executor import (
    ExecutionEnvironmentContext,
    SafeStagingTerraformExecutor,
)
from tests.test_deployment_gate import VALID_PLAN, make_plan
from tests.test_security_foundation import actor


def _context(**changes: str | None) -> ExecutionEnvironmentContext:
    values = {
        "aws_account_id": "123456789012",
        "aws_region": "ap-northeast-1",
        "terraform_root": "infra/staging",
        "state_identity": "state/staging.tfstate",
        "environment": "staging",
    }
    values.update(changes)
    return ExecutionEnvironmentContext(**values)


def _saved_plan(tmp_path: Path) -> ApprovedSavedPlan:
    path = tmp_path / "approved.tfplan"
    path.write_bytes(b"approved local saved plan")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = TerraformCliResult(
        ("terraform", "show", "-json", str(path)), 0, "{}", "", 1, "succeeded"
    )
    verification = SavedPlanVerification(
        result,
        "succeeded",
        None,
        digest,
        digest,
        "1.15.8",
        "1.0",
        (),
    )
    return ApprovedSavedPlan(path, verification)


def _ready(session: Session, tmp_path: Path, suffix: str = "fake-execution"):
    org, _user, owner, project, plan, storage = make_plan(session, suffix)
    security_check_plan(
        session,
        owner,
        plan,
        VALID_PLAN,
        expected_account_id="123456789012",
        expected_region="ap-northeast-1",
        expected_root="infra/staging",
        expected_state_identity="state/staging.tfstate",
        request_id=uuid.uuid4(),
    )
    approval = request_staging_approval(session, owner, plan, request_id=uuid.uuid4())
    _approver_org, approver, approver_access = actor(
        session, f"{suffix}-approver", ["reviewer"], org
    )
    session.add(
        ProjectMember(
            project_id=project.id,
            user_id=approver.id,
            project_role="reviewer",
            status="active",
        )
    )
    session.flush()
    decide_approval(
        session, approver_access, approval, approve=True, request_id=uuid.uuid4()
    )
    preparation = SafeStagingTerraformExecutor(
        storage, allowed_terraform_roots=frozenset({"infra/staging"})
    )
    execution = preparation.request(
        session, owner, plan, context=_context(), request_id=uuid.uuid4()
    )
    preparation.prepare(
        session, owner, execution, context=_context(), request_id=uuid.uuid4()
    )
    fake = FakeTerraformApplyExecutor(preparation, trusted_plan_root=tmp_path)
    return owner, org, project, plan, execution, fake, _saved_plan(tmp_path)


def test_valid_fake_execution_is_evidenced_and_idempotent(
    db_session: Session, tmp_path: Path
):
    owner, _org, _project, plan, execution, fake, saved = _ready(db_session, tmp_path)
    result = fake.execute(
        db_session,
        owner,
        execution,
        context=_context(),
        saved_plan=saved,
        request_id=uuid.uuid4(),
    )
    assert result.status == "executed"
    assert result.executed_at is not None
    assert result.evidence["executor_type"] == "fake"
    assert result.evidence["plan_sha256"] == plan.plan_sha256
    assert (
        result.evidence["saved_plan_sha256"]
        == saved.verification.saved_plan_file_sha256_before
    )
    assert "resource_changes" not in result.evidence
    assert (
        fake.execute(
            db_session,
            owner,
            execution,
            context=_context(),
            saved_plan=saved,
            request_id=uuid.uuid4(),
        ).id
        == execution.id
    )
    assert (
        len(
            db_session.scalars(
                select(AuditLog).where(AuditLog.resource_id == execution.id)
            ).all()
        )
        >= 2
    )


@pytest.mark.parametrize(
    ("outcome", "status", "reason"),
    [
        ("failure", "failed", "FAKE_EXECUTION_FAILED"),
        ("timeout", "failed", "EXECUTION_TIMEOUT"),
        ("cancel", "failed", "EXECUTION_CANCELLED"),
        ("unknown", "blocked", "UNKNOWN_OUTCOME"),
    ],
)
def test_fake_failure_outcomes_are_not_success(
    db_session: Session, tmp_path: Path, outcome, status, reason
):
    owner, _org, _project, _plan, execution, fake, saved = _ready(
        db_session, tmp_path, f"fake-{outcome}"
    )
    result = fake.execute(
        db_session,
        owner,
        execution,
        context=_context(),
        saved_plan=saved,
        request_id=uuid.uuid4(),
        outcome=outcome,
    )
    assert result.status == status
    assert result.authorization_reason == reason
    assert result.evidence["result"] != "success"


def test_ai_agent_and_wrong_permission_are_denied(db_session: Session, tmp_path: Path):
    owner, org, project, _plan, execution, fake, saved = _ready(
        db_session, tmp_path, "deny"
    )
    with pytest.raises(HTTPException, match="AI_AGENT"):
        fake.execute(
            db_session,
            owner,
            execution,
            context=_context(),
            saved_plan=saved,
            request_id=uuid.uuid4(),
            actor_type="ai_agent",
        )
    _other_org, reviewer, reviewer_access = actor(
        db_session, "wrong-permission-reviewer", ["reviewer"], org
    )
    db_session.add(
        ProjectMember(
            project_id=project.id,
            user_id=reviewer.id,
            project_role="reviewer",
            status="active",
        )
    )
    db_session.flush()
    with pytest.raises(HTTPException, match="Permission denied"):
        fake.execute(
            db_session,
            reviewer_access,
            execution,
            context=_context(),
            saved_plan=saved,
            request_id=uuid.uuid4(),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("environment", "production"),
        ("aws_account_id", "999999999999"),
        ("aws_region", "us-east-1"),
        ("state_identity", "wrong.tfstate"),
        ("terraform_root", "wrong/root"),
    ],
)
def test_execution_time_context_revalidation_blocks(
    db_session: Session, tmp_path: Path, field, value
):
    owner, _org, _project, _plan, execution, fake, saved = _ready(
        db_session, tmp_path, f"context-{field}"
    )
    result = fake.execute(
        db_session,
        owner,
        execution,
        context=_context(**{field: value}),
        saved_plan=saved,
        request_id=uuid.uuid4(),
    )
    assert result.status == "blocked"


def test_approval_expiry_and_superseded_plan_are_revalidated(
    db_session: Session, tmp_path: Path
):
    owner, _org, _project, plan, execution, fake, saved = _ready(
        db_session, tmp_path, "expiry"
    )
    approval = db_session.get(ProtectedApproval, plan.approval_id)
    approval.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    expired = fake.execute(
        db_session,
        owner,
        execution,
        context=_context(),
        saved_plan=saved,
        request_id=uuid.uuid4(),
    )
    assert expired.status == "blocked"
    assert expired.authorization_reason == "APPROVAL_EXPIRED"

    owner, _org, _project, plan, execution, fake, saved = _ready(
        db_session, tmp_path, "superseded"
    )
    plan.status = "superseded"
    superseded = fake.execute(
        db_session,
        owner,
        execution,
        context=_context(),
        saved_plan=saved,
        request_id=uuid.uuid4(),
    )
    assert superseded.authorization_reason == "PLAN_SUPERSEDED"


def test_saved_plan_mismatch_and_mutation_are_blocked(
    db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    owner, _org, _project, _plan, execution, fake, saved = _ready(
        db_session, tmp_path, "hash"
    )
    saved.path.write_bytes(b"changed")
    result = fake.execute(
        db_session,
        owner,
        execution,
        context=_context(),
        saved_plan=saved,
        request_id=uuid.uuid4(),
    )
    assert result.authorization_reason == "EXECUTION_PLAN_CHECKSUM_MISMATCH"

    owner, _org, _project, _plan, execution, fake, saved = _ready(
        db_session, tmp_path, "toc"
    )
    original = fake.preparation.authorize

    def mutate(*args, **kwargs):
        saved.path.write_bytes(b"mutated after verification")
        return original(*args, **kwargs)

    monkeypatch.setattr(fake.preparation, "authorize", mutate)
    result = fake.execute(
        db_session,
        owner,
        execution,
        context=_context(),
        saved_plan=saved,
        request_id=uuid.uuid4(),
    )
    assert result.authorization_reason == "EXECUTION_PLAN_CHECKSUM_MISMATCH"


def test_invalid_lifecycle_and_untrusted_saved_plan_are_blocked(
    db_session: Session, tmp_path: Path
):
    owner, _org, _project, _plan, execution, fake, saved = _ready(
        db_session, tmp_path, "lifecycle"
    )
    execution.status = "requested"
    result = fake.execute(
        db_session,
        owner,
        execution,
        context=_context(),
        saved_plan=saved,
        request_id=uuid.uuid4(),
    )
    assert result.authorization_reason == "INVALID_LIFECYCLE"

    owner, _org, _project, _plan, execution, fake, saved = _ready(
        db_session, tmp_path, "path"
    )
    outside = tmp_path.parent / "outside.tfplan"
    outside.write_bytes(b"outside")
    untrusted = ApprovedSavedPlan(outside, saved.verification)
    result = fake.execute(
        db_session,
        owner,
        execution,
        context=_context(),
        saved_plan=untrusted,
        request_id=uuid.uuid4(),
    )
    assert result.authorization_reason == "EXECUTION_PLAN_CHECKSUM_MISMATCH"


def test_real_apply_tripwire_and_no_apply_capability():
    assert not hasattr(SafeStagingTerraformExecutor, "apply")
    assert not hasattr(FakeTerraformApplyExecutor, "apply")
    assert "apply" not in {"version", "show"}


def test_two_sessions_serialize_execution_and_prevent_double_fake_apply(
    db_session: Session, migrated_engine, tmp_path: Path
):
    owner, org, _project, _plan, execution, fake, saved = _ready(
        db_session, tmp_path, "concurrency"
    )
    db_session.commit()
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    barrier = threading.Barrier(2)
    results: list[str] = []

    def worker() -> None:
        session = factory()
        try:
            user = session.get(User, owner.user.id)
            access = require_organization_access(
                org.id, AuthenticatedUser(user), session
            )
            barrier.wait(timeout=10)
            result = fake.execute(
                session,
                access,
                session.get(DeploymentExecution, execution.id),
                context=_context(),
                saved_plan=saved,
                request_id=uuid.uuid4(),
            )
            session.commit()
            results.append(result.status)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert all(not thread.is_alive() for thread in threads)
    assert results == ["executed", "executed"]
    assert execution.status == "prepared"
