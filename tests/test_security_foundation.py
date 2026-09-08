import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.audit import record_audit_log
from app.auth.dependencies import AuthenticatedUser, require_organization_access
from app.auth.permissions import (
    Permission,
    ProtectedAction,
    agent_permissions,
    has_permission,
    permission_context,
    require_permission,
)
from app.auth.verifier import StaticAccessTokenVerifier, VerifiedAccessToken
from app.main import create_app
from app.models import (
    AuditLog,
    MembershipRole,
    Organization,
    OrganizationMembership,
    Project,
    ProjectMember,
    ProtectedApproval,
    Role,
    User,
)
from app.services.approvals import (
    can_execute_protected_action,
    decide_approval,
    request_approval,
)


def actor(
    session: Session,
    suffix: str,
    roles: list[str],
    organization: Organization | None = None,
):
    organization = organization or Organization(name=f"Org {suffix}", status="active")
    user = User(
        cognito_sub=f"security-{suffix}",
        email=f"{suffix}@example.com",
        display_name=suffix,
        status="active",
    )
    membership = OrganizationMembership(
        organization=organization, user=user, status="active"
    )
    session.add(membership)
    for code in roles:
        role = session.scalar(select(Role).where(Role.code == code))
        if role is None:
            role = Role(code=code, display_name=code, is_system=True)
        membership.roles.append(MembershipRole(role=role))
    session.flush()
    return (
        organization,
        user,
        require_organization_access(organization.id, AuthenticatedUser(user), session),
    )


def approval_context(session: Session):
    org, requester, request_access = actor(session, "requester", ["project_manager"])
    _org, approver, approve_access = actor(session, "approver", ["reviewer"], org)
    project = Project(
        organization_id=org.id,
        project_code="SEC-1",
        name="Security",
        status="development",
        current_phase="development",
    )
    session.add(project)
    session.flush()
    session.add_all(
        [
            ProjectMember(
                project_id=project.id,
                user_id=requester.id,
                project_role="project_manager",
                status="active",
            ),
            ProjectMember(
                project_id=project.id,
                user_id=approver.id,
                project_role="reviewer",
                status="active",
            ),
        ]
    )
    session.flush()
    return org, requester, request_access, approver, approve_access, project


def make_approval(
    session: Session,
    request_access,
    project,
    action=ProtectedAction.DEPLOYMENT_PRODUCTION,
):
    return request_approval(
        session,
        request_access,
        organization_id=project.organization_id,
        project_id=project.id,
        action=action,
        resource_type="deployment",
        resource_id=uuid.uuid4(),
        target_version=2,
        reason="security test",
        expires_at=None,
        request_id=uuid.uuid4(),
    )


def test_cross_tenant_access_denied(db_session: Session):
    org, _user, access = actor(db_session, "tenant-a", ["project_manager"])
    other, _other_user, _other_access = actor(db_session, "tenant-b", ["reviewer"])
    with pytest.raises(HTTPException, match="Cross-tenant"):
        request_approval(
            db_session,
            access,
            organization_id=other.id,
            project_id=None,
            action=ProtectedAction.TERRAFORM_PLAN,
            resource_type="terraform",
            resource_id=None,
            target_version=None,
            reason=None,
            expires_at=None,
            request_id=uuid.uuid4(),
        )


def test_viewer_cannot_approve(db_session: Session):
    org, _requester, request_access = actor(
        db_session, "viewer-request", ["organization_admin"]
    )
    _org, _viewer, viewer_access = actor(db_session, "viewer", ["viewer"], org)
    approval = request_approval(
        db_session,
        request_access,
        organization_id=org.id,
        project_id=None,
        action=ProtectedAction.TERRAFORM_PLAN,
        resource_type="terraform",
        resource_id=None,
        target_version=None,
        reason=None,
        expires_at=None,
        request_id=uuid.uuid4(),
    )
    with pytest.raises(HTTPException):
        decide_approval(
            db_session, viewer_access, approval, approve=True, request_id=uuid.uuid4()
        )


def test_four_eyes_and_authorized_reviewer(db_session: Session):
    _org, requester, request_access, _approver, approve_access, project = (
        approval_context(db_session)
    )
    approval = make_approval(db_session, request_access, project)
    with pytest.raises(HTTPException, match="distinct"):
        decide_approval(
            db_session, request_access, approval, approve=True, request_id=uuid.uuid4()
        )
    decide_approval(
        db_session, approve_access, approval, approve=True, request_id=uuid.uuid4()
    )
    assert approval.status == "approved" and approval.decided_by_user_id != requester.id


def test_rejected_expired_stale_and_missing_approval_cannot_execute(
    db_session: Session,
):
    _org, _requester, request_access, _approver, approve_access, project = (
        approval_context(db_session)
    )
    rejected = make_approval(
        db_session, request_access, project, ProtectedAction.TERRAFORM_APPLY
    )
    decide_approval(
        db_session, approve_access, rejected, approve=False, request_id=uuid.uuid4()
    )
    assert not can_execute_protected_action(
        db_session, approve_access, rejected, current_version=2
    )
    expired = make_approval(db_session, request_access, project)
    expired.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert not can_execute_protected_action(
        db_session, approve_access, expired, current_version=2
    )
    stale = make_approval(db_session, request_access, project)
    decide_approval(
        db_session, approve_access, stale, approve=True, request_id=uuid.uuid4()
    )
    assert not can_execute_protected_action(
        db_session, approve_access, stale, current_version=3
    )
    missing = ProtectedApproval(
        organization_id=project.organization_id,
        project_id=project.id,
        requested_by_user_id=request_access.user.id,
        action=ProtectedAction.TERRAFORM_APPLY,
        resource_type="terraform",
        status="requested",
        requires_distinct_approver=True,
    )
    db_session.add(missing)
    db_session.flush()
    assert not can_execute_protected_action(
        db_session, approve_access, missing, current_version=2
    )


def test_ai_agent_has_no_permissions_by_default(db_session: Session):
    _org, _user, access = actor(db_session, "agent", ["viewer"])
    assert agent_permissions() == frozenset()
    with pytest.raises(HTTPException):
        require_permission(db_session, access, Permission.DEPLOYMENT_APPROVE)
    with pytest.raises(HTTPException):
        require_permission(db_session, access, Permission.AI_SETTING_UPDATE)


def test_unknown_role_and_project_roles_cannot_escalate(db_session: Session):
    _org, _user, viewer_access = actor(db_session, "unknown-role", ["viewer"])
    viewer_context = permission_context(db_session, viewer_access)
    assert not has_permission(viewer_context, Permission.PERMISSION_CHANGE)
    assert not has_permission(viewer_context, Permission.AI_SETTING_UPDATE)
    _org, _developer, developer_access = actor(
        db_session, "developer-role", ["developer"]
    )
    assert not has_permission(
        permission_context(db_session, developer_access), Permission.PERMISSION_CHANGE
    )
    _org, _reviewer, reviewer_access = actor(db_session, "reviewer-role", ["reviewer"])
    assert not has_permission(
        permission_context(db_session, reviewer_access), Permission.PERMISSION_CHANGE
    )


def test_approval_audit_events_and_append_only_shape(db_session: Session):
    org, _requester, request_access, _approver, approve_access, project = (
        approval_context(db_session)
    )
    approval = make_approval(db_session, request_access, project)
    decide_approval(
        db_session, approve_access, approval, approve=True, request_id=uuid.uuid4()
    )
    record_audit_log(
        db_session,
        organization_id=org.id,
        actor_user_id=None,
        actor_type="ai_agent",
        approval_id=approval.id,
        correlation_id=approval.id,
        action="security.denied",
        resource_type="deployment",
        request_id=uuid.uuid4(),
        result="denied",
        reason="test",
    )
    events = db_session.scalars(
        select(AuditLog).where(AuditLog.approval_id == approval.id)
    ).all()
    assert {event.action for event in events} >= {
        "approval.requested",
        "approval.approved",
    }
    assert all(event.actor_type in {"human", "ai_agent"} for event in events)
    assert not hasattr(AuditLog, "updated_at")


def api_client(session: Session, user: User, token: str) -> TestClient:
    application = create_app()
    application.state.session_factory = sessionmaker(
        bind=session.get_bind(), expire_on_commit=False
    )
    application.state.token_verifier = StaticAccessTokenVerifier(
        {
            token: VerifiedAccessToken(
                subject=user.cognito_sub,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                claims={"sub": user.cognito_sub},
            )
        }
    )
    return TestClient(application)


def test_approval_api_enforces_tenant_role_and_four_eyes(db_session: Session):
    org, requester, _requester_access = actor(
        db_session, "api-requester", ["organization_admin"]
    )
    _org, reviewer, _reviewer_access = actor(
        db_session, "api-reviewer", ["reviewer"], org
    )
    other_org, outsider, _outsider_access = actor(
        db_session, "api-outsider", ["reviewer"]
    )
    project = Project(
        organization_id=org.id,
        project_code="API-SEC",
        name="API Security",
        status="development",
        current_phase="development",
    )
    db_session.add(project)
    db_session.flush()
    db_session.add(
        ProjectMember(
            project_id=project.id,
            user_id=reviewer.id,
            project_role="reviewer",
            status="active",
        )
    )
    db_session.commit()
    requester_client = api_client(db_session, requester, "requester-token")
    reviewer_client = api_client(db_session, reviewer, "reviewer-token")
    outsider_client = api_client(db_session, outsider, "outsider-token")
    payload = {
        "organization_id": str(org.id),
        "project_id": str(project.id),
        "action": "deployment.production",
        "resource_type": "deployment",
        "target_version": 2,
        "reason": "release",
    }
    created = requester_client.post(
        "/api/v1/approvals",
        headers={"Authorization": "Bearer requester-token"},
        json=payload,
    )
    assert created.status_code == 201, created.text
    approval_id = created.json()["id"]
    assert (
        outsider_client.get(
            f"/api/v1/approvals?organization_id={org.id}",
            headers={"Authorization": "Bearer outsider-token"},
        ).status_code
        == 403
    )
    self_approval = requester_client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"Authorization": "Bearer requester-token"},
        json={},
    )
    assert self_approval.status_code == 403
    approved = reviewer_client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers={"Authorization": "Bearer reviewer-token"},
        json={},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert other_org.id != org.id
