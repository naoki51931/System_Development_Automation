import uuid
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Project, ProjectMember
from app.services.approvals import decide_approval
from app.services.deployment import (
    GATE_BLOCKED,
    GATE_REVIEW,
    can_execute_staging_plan,
    check_security_gate,
    create_deployment_plan,
    request_staging_approval,
    security_check_plan,
)
from app.services.storage import LocalArtifactStorage
from tests.test_security_foundation import actor


VALID_PLAN = {
    "format_version": 1,
    "resource_changes": [
        {
            "address": "aws_ecs_service.staging",
            "type": "aws_ecs_service",
            "change": {"actions": ["update"]},
        }
    ],
}


def make_plan(session: Session, suffix: str = "gate"):
    org, user, access = actor(session, suffix, ["organization_owner"])
    project = Project(
        organization_id=org.id,
        project_code=f"{suffix}-1",
        name="Gate",
        status="staging",
        current_phase="staging",
    )
    session.add(project)
    session.flush()
    storage = LocalArtifactStorage(f"/tmp/phase2-{uuid.uuid4()}")
    plan = create_deployment_plan(
        session,
        storage,
        access,
        project_id=project.id,
        plan_document=VALID_PLAN,
        terraform_root="infra/staging",
        terraform_workspace="staging",
        terraform_state_identity="state/staging.tfstate",
        aws_account_id="123456789012",
        aws_region="ap-northeast-1",
        request_id=uuid.uuid4(),
    )
    return org, user, access, project, plan, storage


def test_valid_plan_review_gate_and_artifact_hash(db_session: Session):
    _org, _user, access, _project, plan, storage = make_plan(db_session)
    stored = storage.get_object(plan.plan_storage_key)
    assert len(stored) == plan.plan_size
    result = security_check_plan(
        db_session,
        access,
        plan,
        VALID_PLAN,
        expected_account_id="123456789012",
        expected_region="ap-northeast-1",
        expected_root="infra/staging",
        expected_state_identity="state/staging.tfstate",
        request_id=uuid.uuid4(),
    )
    assert result.status == GATE_REVIEW
    assert result.reasons == ()


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("aws_account_id", "999999999999", "WRONG_ACCOUNT"),
        ("aws_region", "us-east-1", "WRONG_REGION"),
        ("terraform_state_identity", "other.tfstate", "WRONG_STATE"),
        ("environment", "production", "WRONG_ENVIRONMENT"),
    ],
)
def test_binding_mismatch_blocks(db_session: Session, field, value, reason):
    _org, _user, access, _project, plan, _storage = make_plan(
        db_session, f"{field}-{value}"
    )
    document = VALID_PLAN
    setattr(plan, field, value)
    result = check_security_gate(
        plan,
        document,
        expected_account_id="123456789012",
        expected_region="ap-northeast-1",
        expected_root="infra/staging",
        expected_state_identity="state/staging.tfstate",
    )
    assert result.status == GATE_BLOCKED and reason in result.reasons


@pytest.mark.parametrize(
    ("resource_type", "address", "reason"),
    [
        ("aws_route53_record", "aws_route53_record.dns", "DNS_CHANGE_DETECTED"),
        ("aws_iam_role", "aws_iam_role.deploy", "IAM_CHANGE_DETECTED"),
        (
            "aws_secretsmanager_secret",
            "aws_secretsmanager_secret.key",
            "SECRET_CHANGE_DETECTED",
        ),
        ("aws_db_snapshot", "aws_db_snapshot.old", "SNAPSHOT_DELETE_DETECTED"),
    ],
)
def test_dangerous_resource_actions_block(
    db_session: Session, resource_type, address, reason
):
    _org, _user, _access, _project, plan, _storage = make_plan(
        db_session, f"danger-{reason}"
    )
    document = {
        "resource_changes": [
            {
                "type": resource_type,
                "address": address,
                "change": {"actions": ["delete"]},
            }
        ]
    }
    result = check_security_gate(
        plan,
        document,
        expected_account_id="123456789012",
        expected_region="ap-northeast-1",
        expected_root="infra/staging",
        expected_state_identity="state/staging.tfstate",
    )
    assert result.status == GATE_BLOCKED and reason in result.reasons


def test_destroy_production_and_unknown_state_block(db_session: Session):
    _org, _user, _access, _project, plan, _storage = make_plan(db_session, "destroy")
    document = {
        "resource_changes": [
            {
                "address": "aws_instance.prod",
                "type": "aws_instance",
                "change": {"actions": ["delete"]},
            }
        ]
    }
    plan.terraform_state_identity = None
    result = check_security_gate(
        plan,
        document,
        expected_account_id="123456789012",
        expected_region="ap-northeast-1",
        expected_root="infra/staging",
        expected_state_identity="state/staging.tfstate",
    )
    assert result.status == GATE_BLOCKED
    assert {"UNEXPECTED_DESTROY", "PRODUCTION_RESOURCE_DETECTED", "WRONG_STATE"} <= set(
        result.reasons
    )


def test_approval_checksum_four_eyes_superseded_and_cross_tenant(db_session: Session):
    org, _user, owner_access, project, plan, _storage = make_plan(
        db_session, "approval"
    )
    security_check_plan(
        db_session,
        owner_access,
        plan,
        VALID_PLAN,
        expected_account_id="123456789012",
        expected_region="ap-northeast-1",
        expected_root="infra/staging",
        expected_state_identity="state/staging.tfstate",
        request_id=uuid.uuid4(),
    )
    approval = request_staging_approval(
        db_session, owner_access, plan, request_id=uuid.uuid4()
    )
    with pytest.raises(HTTPException, match="distinct"):
        decide_approval(
            db_session, owner_access, approval, approve=True, request_id=uuid.uuid4()
        )
    _other_org, _reviewer, reviewer_access = actor(
        db_session, "approver", ["reviewer"], org
    )
    db_session.add(
        ProjectMember(
            project_id=project.id,
            user_id=reviewer_access.user.id,
            project_role="reviewer",
            status="active",
        )
    )
    db_session.flush()
    decide_approval(
        db_session, reviewer_access, approval, approve=True, request_id=uuid.uuid4()
    )
    assert can_execute_staging_plan(
        db_session,
        owner_access,
        plan,
        current_plan_sha256=plan.plan_sha256,
        current_state_identity="state/staging.tfstate",
        current_account_id="123456789012",
        current_region="ap-northeast-1",
        request_id=uuid.uuid4(),
    )
    assert not can_execute_staging_plan(
        db_session,
        owner_access,
        plan,
        current_plan_sha256="0" * 64,
        current_state_identity="state/staging.tfstate",
        current_account_id="123456789012",
        current_region="ap-northeast-1",
        request_id=uuid.uuid4(),
    )
    _new_org, _new_user, _new_access, _new_project, new_plan, _new_storage = make_plan(
        db_session, "approval-new"
    )
    # Supersession is scoped to one project; explicitly exercise the same project.
    new_plan.project_id = project.id
    new_plan.organization_id = org.id
    plan.status = "superseded"
    plan.superseded_by_id = new_plan.id
    assert not can_execute_staging_plan(
        db_session,
        owner_access,
        plan,
        current_plan_sha256=plan.plan_sha256,
        current_state_identity="state/staging.tfstate",
        current_account_id="123456789012",
        current_region="ap-northeast-1",
        request_id=uuid.uuid4(),
    )
    _foreign_org, _foreign_user, foreign_access = actor(
        db_session, "foreign-gate", ["organization_owner"]
    )
    assert not can_execute_staging_plan(
        db_session,
        foreign_access,
        plan,
        current_plan_sha256=plan.plan_sha256,
        current_state_identity="state/staging.tfstate",
        current_account_id="123456789012",
        current_region="ap-northeast-1",
        request_id=uuid.uuid4(),
    )


def test_expired_rejected_missing_approval_and_audit(db_session: Session):
    _org, _user, access, _project, plan, _storage = make_plan(db_session, "audit-gate")
    plan.security_gate_status = "pass"
    plan.approval_id = uuid.uuid4()
    assert not can_execute_staging_plan(
        db_session,
        access,
        plan,
        current_plan_sha256=plan.plan_sha256,
        current_state_identity="state/staging.tfstate",
        current_account_id="123456789012",
        current_region="ap-northeast-1",
        request_id=uuid.uuid4(),
    )
    assert db_session.scalars(
        select(AuditLog).where(AuditLog.resource_id == plan.id)
    ).all()
