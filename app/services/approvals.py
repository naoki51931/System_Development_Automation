from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.audit import record_audit_log
from app.auth.permissions import (
    Permission,
    ProtectedAction,
    requires_distinct_approver,
    require_permission,
)
from app.auth.dependencies import OrganizationAccess
from app.models import Project, ProtectedApproval


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(
    session: Session,
    approval: ProtectedApproval,
    action: str,
    actor_id: uuid.UUID | None,
    request_id: uuid.UUID,
    result: str,
    reason: str | None = None,
    ip_address: str | None = None,
) -> None:
    record_audit_log(
        session,
        organization_id=approval.organization_id,
        actor_user_id=actor_id,
        actor_type="human",
        approval_id=approval.id,
        correlation_id=approval.id,
        action=action,
        resource_type=approval.resource_type,
        resource_id=approval.resource_id,
        request_id=request_id,
        result=result,
        reason=reason,
        ip_address=ip_address,
        after={"status": approval.status, "action": approval.action},
    )


def request_approval(
    session: Session,
    access: OrganizationAccess,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID | None,
    action: ProtectedAction,
    resource_type: str,
    resource_id: uuid.UUID | None,
    target_version: int | None,
    reason: str | None,
    expires_at: datetime | None,
    request_id: uuid.UUID,
    ip_address: str | None = None,
    plan_checksum: str | None = None,
    artifact_digest: str | None = None,
) -> ProtectedApproval:
    if access.membership.organization_id != organization_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant access denied")
    if project_id is not None:
        project = session.get(Project, project_id)
        if project is None or project.organization_id != organization_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant access denied")
    if not isinstance(action, ProtectedAction):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown protected action"
        )
    require_permission(session, access, Permission.APPROVAL_REQUEST, project_id)
    approval = ProtectedApproval(
        organization_id=organization_id,
        project_id=project_id,
        requested_by_user_id=access.user.id,
        action=action.value,
        resource_type=resource_type,
        resource_id=resource_id,
        target_version=target_version,
        plan_checksum=plan_checksum,
        artifact_digest=artifact_digest,
        reason=reason,
        expires_at=expires_at,
        requires_distinct_approver=requires_distinct_approver(action),
    )
    session.add(approval)
    session.flush()
    _audit(
        session,
        approval,
        "approval.requested",
        access.user.id,
        request_id,
        "success",
        ip_address=ip_address,
    )
    return approval


def decide_approval(
    session: Session,
    access: OrganizationAccess,
    approval: ProtectedApproval,
    *,
    approve: bool,
    request_id: uuid.UUID,
    reason: str | None = None,
    ip_address: str | None = None,
) -> ProtectedApproval:
    if approval.organization_id != access.membership.organization_id:
        _audit(
            session,
            approval,
            "approval.decided",
            access.user.id,
            request_id,
            "denied",
            "Cross-tenant access denied",
            ip_address=ip_address,
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant access denied")
    try:
        required = (
            Permission.APPROVAL_APPROVE if approve else Permission.APPROVAL_REJECT
        )
        require_permission(session, access, required, approval.project_id)
    except HTTPException:
        _audit(
            session,
            approval,
            "approval.decided",
            access.user.id,
            request_id,
            "denied",
            "Permission denied",
            ip_address=ip_address,
        )
        raise
    if approval.status != "requested":
        _audit(
            session,
            approval,
            "approval.decided",
            access.user.id,
            request_id,
            "denied",
            "Approval is not requestable",
            ip_address=ip_address,
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Approval is no longer requestable"
        )
    now = _now()
    if approval.expires_at is not None and approval.expires_at <= now:
        approval.status = "expired"
        approval.decided_at = now
        _audit(
            session,
            approval,
            "approval.expired",
            access.user.id,
            request_id,
            "denied",
            "Approval expired",
            ip_address=ip_address,
        )
        raise HTTPException(status.HTTP_409_CONFLICT, "Approval expired")
    if (
        approve
        and approval.requires_distinct_approver
        and approval.requested_by_user_id == access.user.id
    ):
        _audit(
            session,
            approval,
            "approval.decided",
            access.user.id,
            request_id,
            "denied",
            "Four-eyes policy requires a distinct approver",
            ip_address=ip_address,
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "A distinct approver is required"
        )
    approval.status = "approved" if approve else "rejected"
    approval.decided_by_user_id = access.user.id
    approval.decided_at = now
    approval.reason = reason or approval.reason
    if approval.resource_type == "deployment_plan" and approval.resource_id:
        from app.models.deployment import DeploymentPlan

        plan = session.get(DeploymentPlan, approval.resource_id)
        if plan is not None and plan.approval_id == approval.id:
            plan.status = "approved" if approve else "created"
            record_audit_log(
                session,
                organization_id=plan.organization_id,
                actor_user_id=access.user.id,
                action=(
                    "deployment.plan.approved"
                    if approve
                    else "deployment.plan.rejected"
                ),
                resource_type="deployment_plan",
                resource_id=plan.id,
                approval_id=approval.id,
                correlation_id=approval.id,
                request_id=request_id,
                after={"status": plan.status, "plan_sha256": plan.plan_sha256},
                result="success",
                reason=reason,
            )
    _audit(
        session,
        approval,
        "approval.approved" if approve else "approval.rejected",
        access.user.id,
        request_id,
        "success",
        reason,
        ip_address=ip_address,
    )
    return approval


def can_execute_protected_action(
    session: Session,
    access: OrganizationAccess,
    approval: ProtectedApproval,
    *,
    current_version: int | None = None,
) -> bool:
    """Authorize a future executor; this function performs no protected action."""

    if approval.organization_id != access.membership.organization_id:
        return False
    if approval.status != "approved":
        return False
    if approval.expires_at is not None and approval.expires_at <= _now():
        approval.status = "expired"
        return False
    if (
        approval.target_version is not None
        and approval.target_version != current_version
    ):
        return False
    # An executor must have an explicit permission as well as an approval.
    permission = (
        Permission.PERMISSION_CHANGE
        if approval.action == ProtectedAction.PERMISSION_CHANGE
        else Permission.DEPLOYMENT_REQUEST
    )
    try:
        require_permission(session, access, permission, approval.project_id)
    except HTTPException:
        return False
    return True
