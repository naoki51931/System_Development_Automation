import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuditLog, DeploymentExecution, ProjectMember
from app.services.approvals import decide_approval
from app.services.terraform_executor import (
    ExecutionEnvironmentContext,
    SafeStagingTerraformExecutor,
)
from tests.test_deployment_gate import VALID_PLAN, make_plan
from tests.test_security_foundation import actor
from app.services.deployment import request_staging_approval, security_check_plan


def ready(db_session: Session, suffix: str = "executor"):
    org, _user, owner, project, plan, storage = make_plan(db_session, suffix)
    security_check_plan(
        db_session,
        owner,
        plan,
        VALID_PLAN,
        expected_account_id="123456789012",
        expected_region="ap-northeast-1",
        expected_root="infra/staging",
        expected_state_identity="state/staging.tfstate",
        request_id=uuid.uuid4(),
    )
    approval = request_staging_approval(
        db_session, owner, plan, request_id=uuid.uuid4()
    )
    _approver_org, approver, approver_access = actor(
        db_session, f"{suffix}-approver", ["reviewer"], org
    )
    db_session.add(
        ProjectMember(
            project_id=project.id,
            user_id=approver.id,
            project_role="reviewer",
            status="active",
        )
    )
    db_session.flush()
    decide_approval(
        db_session, approver_access, approval, approve=True, request_id=uuid.uuid4()
    )
    return owner, plan, storage


def context(
    root: str = "infra/staging", **changes: str | None
) -> ExecutionEnvironmentContext:
    values = {
        "aws_account_id": "123456789012",
        "aws_region": "ap-northeast-1",
        "terraform_root": root,
        "state_identity": "state/staging.tfstate",
        "environment": "staging",
    }
    values.update(changes)
    return ExecutionEnvironmentContext(**values)


def test_valid_staging_execution_prepares_and_is_idempotent(db_session: Session):
    owner, plan, storage = ready(db_session)
    executor = SafeStagingTerraformExecutor(
        storage, allowed_terraform_roots=frozenset({"infra/staging"})
    )
    execution = executor.request(
        db_session, owner, plan, context=context(), request_id=uuid.uuid4()
    )
    prepared = executor.prepare(
        db_session, owner, execution, context=context(), request_id=uuid.uuid4()
    )
    assert prepared.status == "prepared"
    assert prepared.authorization_result == "AUTHORIZED_FOR_STAGING_EXECUTION"
    assert prepared.executed_at is None
    assert (
        executor.prepare(
            db_session, owner, execution, context=context(), request_id=uuid.uuid4()
        ).id
        == execution.id
    )
    assert {
        event.action
        for event in db_session.scalars(
            select(AuditLog).where(AuditLog.resource_id == execution.id)
        ).all()
    } >= {
        "deployment.execution.requested",
        "deployment.execution.validation_started",
        "deployment.execution.authorized",
        "deployment.execution.prepared",
    }


def test_toc_tamper_between_authorize_and_prepare_is_blocked(db_session: Session):
    owner, plan, storage = ready(db_session, "toc")
    executor = SafeStagingTerraformExecutor(
        storage, allowed_terraform_roots=frozenset({"infra/staging"})
    )
    execution = executor.request(
        db_session, owner, plan, context=context(), request_id=uuid.uuid4()
    )
    executor.authorize(
        db_session, owner, execution, context=context(), request_id=uuid.uuid4()
    )
    storage.put_object(
        plan.plan_storage_key,
        b'{"resource_changes":[],"tampered":true}',
        "application/json",
    )
    prepared = executor.prepare(
        db_session, owner, execution, context=context(), request_id=uuid.uuid4()
    )
    assert prepared.status == "blocked"
    assert prepared.authorization_reason == "PLAN_CHECKSUM_MISMATCH"


def test_context_and_policy_fail_closed(db_session: Session):
    owner, plan, storage = ready(db_session, "context")
    executor = SafeStagingTerraformExecutor(
        storage, allowed_terraform_roots=frozenset({"infra/staging"})
    )
    cases = [("production", "WRONG_ENVIRONMENT"), ("staging", "WRONG_ACCOUNT")]
    for index, (environment, expected) in enumerate(cases):
        execution = executor.request(
            db_session, owner, plan, context=context(), request_id=uuid.uuid4()
        )
        if expected == "WRONG_ACCOUNT":
            bad = context(aws_account_id="999999999999")
        else:
            bad = context(environment=environment)
        assert (
            executor.prepare(
                db_session, owner, execution, context=bad, request_id=uuid.uuid4()
            ).authorization_reason
            == expected
        )
        if index == 0:
            plan.status = "approved"


def test_root_traversal_and_ai_agent_are_rejected(db_session: Session):
    owner, plan, storage = ready(db_session, "policy")
    executor = SafeStagingTerraformExecutor(
        storage,
        allowed_terraform_roots=frozenset({"infra/staging"}),
        repository_root=Path("/tmp"),
    )
    execution = executor.request(
        db_session, owner, plan, context=context(), request_id=uuid.uuid4()
    )
    assert (
        executor.prepare(
            db_session,
            owner,
            execution,
            context=context(root="../infra/staging"),
            request_id=uuid.uuid4(),
        ).authorization_reason
        == "WRONG_TERRAFORM_ROOT"
    )
    with pytest.raises(Exception) as exc_info:
        executor.request(
            db_session,
            owner,
            plan,
            context=context(),
            request_id=uuid.uuid4(),
            actor_type="ai_agent",
        )
    assert getattr(exc_info.value, "detail", "") == "AI_AGENT cannot invoke executor"


def test_active_execution_unique_constraint_blocks_duplicate_collision(
    db_session: Session,
):
    owner, plan, storage = ready(db_session, "unique-collision")
    executor = SafeStagingTerraformExecutor(
        storage, allowed_terraform_roots=frozenset({"infra/staging"})
    )
    first = executor.request(
        db_session, owner, plan, context=context(), request_id=uuid.uuid4()
    )
    db_session.commit()

    duplicate = DeploymentExecution(
        organization_id=first.organization_id,
        project_id=first.project_id,
        deployment_plan_id=first.deployment_plan_id,
        approval_id=first.approval_id,
        requested_by=first.requested_by,
        plan_sha256=first.plan_sha256,
        expected_account_id=first.expected_account_id,
        expected_region=first.expected_region,
        expected_state_identity=first.expected_state_identity,
        expected_terraform_root=first.expected_terraform_root,
        status="requested",
        correlation_id=uuid.uuid4(),
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    assert db_session.get(DeploymentExecution, first.id) is not None
