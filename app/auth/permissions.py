"""Backend permission matrix and protected-action policy.

This module is deliberately deny-by-default.  It contains policy only; it does
not execute deployment, Terraform, or agent operations.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import OrganizationAccess
from app.models import ProjectMember


class ActorType(StrEnum):
    HUMAN = "human"
    SYSTEM = "system"
    AI_AGENT = "ai_agent"


class Permission(StrEnum):
    PROJECT_READ = "project.read"
    PROJECT_UPDATE = "project.update"
    ARTIFACT_READ = "artifact.read"
    ARTIFACT_CREATE = "artifact.create"
    ARTIFACT_UPDATE = "artifact.update"
    ARTIFACT_REVIEW = "artifact.review"
    APPROVAL_READ = "approval.read"
    APPROVAL_REQUEST = "approval.request"
    APPROVAL_APPROVE = "approval.approve"
    APPROVAL_REJECT = "approval.reject"
    AUDIT_READ = "audit.read"
    DEPLOYMENT_READ = "deployment.read"
    DEPLOYMENT_REQUEST = "deployment.request"
    DEPLOYMENT_APPROVE = "deployment.approve"
    SECURITY_GATE_READ = "security_gate.read"
    PERMISSION_CHANGE = "permission.change"
    AI_SETTING_UPDATE = "ai_setting.update"
    CONTRACT_CREATE = "contract.create"
    CONTRACT_UPDATE = "contract.update"
    PAYMENT_UPDATE = "payment.update"
    DEPLOYMENT_PLAN_CREATE = "deployment.plan.create"
    DEPLOYMENT_SECURITY_CHECK = "deployment.security_check"
    DEPLOYMENT_EXECUTE_AUTHORIZE = "deployment.execute_authorize"


class ProtectedAction(StrEnum):
    DEPLOYMENT_STAGING = "deployment.staging"
    DEPLOYMENT_PRODUCTION = "deployment.production"
    TERRAFORM_PLAN = "terraform.plan"
    TERRAFORM_APPLY = "terraform.apply"
    SECRET_ACCESS = "secret.access"  # nosec B105 - permission identifier, not a secret
    PERMISSION_CHANGE = "permission.change"


PROTECTED_ACTIONS = frozenset(ProtectedAction)

# Organization roles are intentionally the existing seeded role names.
ORGANIZATION_ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "organization_owner": frozenset(Permission),
    "organization_admin": frozenset(
        {
            Permission.PROJECT_READ,
            Permission.PROJECT_UPDATE,
            Permission.ARTIFACT_READ,
            Permission.ARTIFACT_CREATE,
            Permission.ARTIFACT_UPDATE,
            Permission.ARTIFACT_REVIEW,
            Permission.APPROVAL_READ,
            Permission.APPROVAL_REQUEST,
            Permission.APPROVAL_APPROVE,
            Permission.APPROVAL_REJECT,
            Permission.AUDIT_READ,
            Permission.DEPLOYMENT_READ,
            Permission.DEPLOYMENT_REQUEST,
            Permission.DEPLOYMENT_APPROVE,
            Permission.SECURITY_GATE_READ,
            Permission.PERMISSION_CHANGE,
            Permission.AI_SETTING_UPDATE,
            Permission.CONTRACT_CREATE,
            Permission.CONTRACT_UPDATE,
            Permission.PAYMENT_UPDATE,
            Permission.DEPLOYMENT_PLAN_CREATE,
            Permission.DEPLOYMENT_SECURITY_CHECK,
            Permission.DEPLOYMENT_EXECUTE_AUTHORIZE,
        }
    ),
    # The existing application stores project_manager as an organization
    # membership role for project creation. Keep that behavior while the
    # project-scoped lookup below remains authoritative for project resources.
    "project_manager": frozenset(
        {
            Permission.PROJECT_READ,
            Permission.PROJECT_UPDATE,
            Permission.ARTIFACT_READ,
            Permission.ARTIFACT_CREATE,
            Permission.ARTIFACT_UPDATE,
            Permission.ARTIFACT_REVIEW,
            Permission.APPROVAL_READ,
            Permission.APPROVAL_REQUEST,
            Permission.APPROVAL_APPROVE,
            Permission.APPROVAL_REJECT,
            Permission.DEPLOYMENT_READ,
            Permission.DEPLOYMENT_REQUEST,
            Permission.SECURITY_GATE_READ,
            Permission.AI_SETTING_UPDATE,
            Permission.CONTRACT_CREATE,
            Permission.CONTRACT_UPDATE,
            Permission.PAYMENT_UPDATE,
            Permission.DEPLOYMENT_PLAN_CREATE,
            Permission.DEPLOYMENT_SECURITY_CHECK,
            Permission.DEPLOYMENT_EXECUTE_AUTHORIZE,
        }
    ),
}

PROJECT_ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "project_manager": frozenset(
        {
            Permission.PROJECT_READ,
            Permission.PROJECT_UPDATE,
            Permission.ARTIFACT_READ,
            Permission.ARTIFACT_CREATE,
            Permission.ARTIFACT_UPDATE,
            Permission.ARTIFACT_REVIEW,
            Permission.APPROVAL_READ,
            Permission.APPROVAL_REQUEST,
            Permission.APPROVAL_APPROVE,
            Permission.APPROVAL_REJECT,
            Permission.DEPLOYMENT_READ,
            Permission.DEPLOYMENT_REQUEST,
            Permission.SECURITY_GATE_READ,
            Permission.AI_SETTING_UPDATE,
            Permission.CONTRACT_CREATE,
            Permission.CONTRACT_UPDATE,
            Permission.PAYMENT_UPDATE,
            Permission.DEPLOYMENT_PLAN_CREATE,
            Permission.DEPLOYMENT_SECURITY_CHECK,
            Permission.DEPLOYMENT_EXECUTE_AUTHORIZE,
        }
    ),
    "reviewer": frozenset(
        {
            Permission.PROJECT_READ,
            Permission.ARTIFACT_READ,
            Permission.ARTIFACT_REVIEW,
            Permission.APPROVAL_READ,
            Permission.APPROVAL_REQUEST,
            Permission.APPROVAL_APPROVE,
            Permission.APPROVAL_REJECT,
            Permission.SECURITY_GATE_READ,
        }
    ),
    "developer": frozenset(
        {
            Permission.PROJECT_READ,
            Permission.ARTIFACT_READ,
            Permission.ARTIFACT_CREATE,
            Permission.ARTIFACT_UPDATE,
        }
    ),
    "customer": frozenset(
        {
            Permission.PROJECT_READ,
            Permission.ARTIFACT_READ,
            Permission.APPROVAL_READ,
            Permission.APPROVAL_APPROVE,
            Permission.APPROVAL_REJECT,
            Permission.CONTRACT_UPDATE,
            Permission.PAYMENT_UPDATE,
        }
    ),
    "viewer": frozenset({Permission.PROJECT_READ, Permission.ARTIFACT_READ}),
}


@dataclass(frozen=True)
class PermissionContext:
    access: OrganizationAccess
    project_roles: frozenset[str] = frozenset()


def permission_context(
    session: Session,
    access: OrganizationAccess,
    project_id: uuid.UUID | None = None,
) -> PermissionContext:
    if project_id is None:
        return PermissionContext(access)
    member_roles = session.scalars(
        select(ProjectMember.project_role).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == access.user.id,
            ProjectMember.status == "active",
        )
    ).all()
    return PermissionContext(access, frozenset(member_roles))


def has_permission(context: PermissionContext, permission: Permission) -> bool:
    if context.access.user.status != "active":
        return False
    permissions: set[Permission] = set()
    for role in context.access.role_codes:
        permissions.update(ORGANIZATION_ROLE_PERMISSIONS.get(role, frozenset()))
    for role in context.project_roles:
        permissions.update(PROJECT_ROLE_PERMISSIONS.get(role, frozenset()))
    return permission in permissions


def require_permission(
    session: Session,
    access: OrganizationAccess,
    permission: Permission,
    project_id: uuid.UUID | None = None,
) -> PermissionContext:
    context = permission_context(session, access, project_id)
    if not has_permission(context, permission):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission denied")
    return context


def requires_distinct_approver(action: ProtectedAction) -> bool:
    return action in {
        ProtectedAction.DEPLOYMENT_STAGING,
        ProtectedAction.DEPLOYMENT_PRODUCTION,
        ProtectedAction.TERRAFORM_APPLY,
        ProtectedAction.SECRET_ACCESS,
        ProtectedAction.PERMISSION_CHANGE,
    }


def agent_permissions() -> frozenset[Permission]:
    """AI_AGENT has no permissions until a future, explicit policy grants one."""

    return frozenset()
