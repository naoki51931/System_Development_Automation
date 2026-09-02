from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit_log
from app.auth.dependencies import OrganizationAccess
from app.auth.permissions import Permission, ProtectedAction, require_permission
from app.models import DeploymentPlan, ProtectedApproval, Project
from app.services.approvals import request_approval
from app.services.storage import ArtifactStorage

GATE_PASS = "pass"  # nosec B105 - security gate status, not a password
GATE_REVIEW = "review_required"
GATE_BLOCKED = "blocked"


@dataclass(frozen=True)
class GateResult:
    status: str
    reasons: tuple[str, ...]
    summary: dict[str, Any]


@dataclass(frozen=True)
class ExecutionDecision:
    allowed: bool
    reason: str | None = None


def canonical_plan_bytes(plan: dict[str, Any]) -> bytes:
    return json.dumps(
        plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def plan_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _resource_changes(plan: dict[str, Any]) -> list[dict[str, Any]]:
    changes = plan.get("resource_changes", [])
    return [item for item in changes if isinstance(item, dict)]


def summarize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    counts = {"add": 0, "change": 0, "replace": 0, "destroy": 0}
    resources: list[dict[str, str]] = []
    for item in _resource_changes(plan):
        change = item.get("change") if isinstance(item.get("change"), dict) else item
        actions = change.get("actions", []) if isinstance(change, dict) else []
        actions = [str(action) for action in actions]
        address = str(item.get("address", "unknown"))
        resource_type = str(item.get("type", ""))
        if actions == ["create"]:
            counts["add"] += 1
        elif actions == ["update"]:
            counts["change"] += 1
        elif "delete" in actions and "create" in actions:
            counts["replace"] += 1
        elif "delete" in actions:
            counts["destroy"] += 1
        resources.append(
            {"address": address, "type": resource_type, "action": ",".join(actions)}
        )
    return {**counts, "resources": resources}


def _contains_hint(item: object, hints: tuple[str, ...]) -> bool:
    if isinstance(item, dict):
        return any(
            _contains_hint(key, hints) or _contains_hint(value, hints)
            for key, value in item.items()
        )
    if isinstance(item, list):
        return any(_contains_hint(value, hints) for value in item)
    return any(hint in str(item).lower() for hint in hints)


def check_security_gate(
    plan: DeploymentPlan,
    plan_document: dict[str, Any],
    *,
    expected_account_id: str,
    expected_region: str,
    expected_root: str,
    expected_state_identity: str,
) -> GateResult:
    summary = summarize_plan(plan_document)
    reasons: list[str] = []
    if plan.environment != "staging" or plan.target_environment != "staging":
        reasons.append("WRONG_ENVIRONMENT")
    if plan.aws_account_id != expected_account_id:
        reasons.append("WRONG_ACCOUNT")
    if plan.aws_region != expected_region:
        reasons.append("WRONG_REGION")
    if (
        not plan.terraform_state_identity
        or plan.terraform_state_identity != expected_state_identity
    ):
        reasons.append("WRONG_STATE")
    if plan.terraform_root != expected_root:
        reasons.append("WRONG_TERRAFORM_ROOT")
    if _contains_hint(plan_document, ("production", "prod", "prod-", "prod/")):
        reasons.append("PRODUCTION_RESOURCE_DETECTED")
    if _contains_hint(plan_document, ("route53", "route_53", "dns")):
        reasons.append("DNS_CHANGE_DETECTED")
    if _contains_hint(plan_document, ("iam", "identity_access")):
        reasons.append("IAM_CHANGE_DETECTED")
    if _contains_hint(plan_document, ("secret", "secretsmanager", "ssm_parameter")):
        reasons.append("SECRET_CHANGE_DETECTED")
    if summary["destroy"] and _contains_hint(plan_document, ("snapshot",)):
        reasons.append("SNAPSHOT_DELETE_DETECTED")
    if summary["destroy"]:
        reasons.append("UNEXPECTED_DESTROY")
    gate_status = (
        GATE_BLOCKED
        if reasons
        else (
            GATE_REVIEW
            if summary["add"] or summary["change"] or summary["replace"]
            else GATE_PASS
        )
    )
    return GateResult(gate_status, tuple(dict.fromkeys(reasons)), summary)


def create_deployment_plan(
    session: Session,
    storage: ArtifactStorage,
    access: OrganizationAccess,
    *,
    project_id: uuid.UUID,
    plan_document: dict[str, Any],
    terraform_root: str,
    terraform_workspace: str | None,
    terraform_state_identity: str | None,
    aws_account_id: str | None,
    aws_region: str | None,
    request_id: uuid.UUID,
) -> DeploymentPlan:
    require_permission(session, access, Permission.DEPLOYMENT_PLAN_CREATE, project_id)
    project = session.get(Project, project_id)
    if project is None or project.organization_id != access.membership.organization_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Project access denied")
    content = canonical_plan_bytes(plan_document)
    plan = DeploymentPlan(
        organization_id=project.organization_id,
        project_id=project.id,
        environment="staging",
        target_environment="staging",
        created_by_user_id=access.user.id,
        plan_storage_key=f"organizations/{project.organization_id}/projects/{project.id}/deployment-plans/{uuid.uuid4()}.json",
        plan_sha256=plan_sha256(content),
        plan_size=len(content),
        terraform_root=terraform_root,
        terraform_workspace=terraform_workspace,
        terraform_state_identity=terraform_state_identity,
        aws_account_id=aws_account_id,
        aws_region=aws_region,
        plan_summary=summarize_plan(plan_document),
        add_count=summarize_plan(plan_document)["add"],
        change_count=summarize_plan(plan_document)["change"],
        replace_count=summarize_plan(plan_document)["replace"],
        destroy_count=summarize_plan(plan_document)["destroy"],
    )
    storage.put_object(plan.plan_storage_key, content, "application/json")
    latest = session.scalars(
        select(DeploymentPlan).where(
            DeploymentPlan.organization_id == project.organization_id,
            DeploymentPlan.project_id == project.id,
            DeploymentPlan.environment == "staging",
            DeploymentPlan.status.in_(
                ("created", "security_checked", "approval_requested", "approved")
            ),
        )
    ).all()
    session.add(plan)
    session.flush()
    for old in latest:
        old.status = "superseded"
        old.superseded_by_id = plan.id
    record_audit_log(
        session,
        organization_id=plan.organization_id,
        actor_user_id=access.user.id,
        action="deployment.plan.created",
        resource_type="deployment_plan",
        resource_id=plan.id,
        request_id=request_id,
        correlation_id=plan.id,
        after={
            "plan_sha256": plan.plan_sha256,
            "environment": "staging",
            "plan_size": plan.plan_size,
        },
        result="success",
    )
    return plan


def security_check_plan(
    session: Session,
    access: OrganizationAccess,
    plan: DeploymentPlan,
    plan_document: dict[str, Any],
    *,
    expected_account_id: str,
    expected_region: str,
    expected_root: str,
    expected_state_identity: str,
    request_id: uuid.UUID,
) -> GateResult:
    require_permission(
        session, access, Permission.DEPLOYMENT_SECURITY_CHECK, plan.project_id
    )
    if plan.organization_id != access.membership.organization_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant access denied")
    if plan_sha256(canonical_plan_bytes(plan_document)) != plan.plan_sha256:
        result = GateResult(
            GATE_BLOCKED,
            ("PLAN_CHECKSUM_MISMATCH",),
            summarize_plan(plan_document),
        )
    else:
        result = check_security_gate(
            plan,
            plan_document,
            expected_account_id=expected_account_id,
            expected_region=expected_region,
            expected_root=expected_root,
            expected_state_identity=expected_state_identity,
        )
    plan.security_gate_status = result.status
    plan.security_gate_result = {
        "status": result.status,
        "reasons": list(result.reasons),
        "summary": result.summary,
    }
    plan.status = "security_checked"
    record_audit_log(
        session,
        organization_id=plan.organization_id,
        actor_user_id=access.user.id,
        action="deployment.plan.security_checked",
        resource_type="deployment_plan",
        resource_id=plan.id,
        request_id=request_id,
        correlation_id=plan.id,
        after={
            "plan_sha256": plan.plan_sha256,
            "security_gate_status": result.status,
            "reasons": list(result.reasons),
        },
        result=result.status,
        reason=",".join(result.reasons) or None,
    )
    return result


def request_staging_approval(
    session: Session,
    access: OrganizationAccess,
    plan: DeploymentPlan,
    *,
    request_id: uuid.UUID,
) -> ProtectedApproval:
    require_permission(session, access, Permission.DEPLOYMENT_REQUEST, plan.project_id)
    if plan.organization_id != access.membership.organization_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant access denied")
    if plan.security_gate_status == GATE_BLOCKED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Security gate is blocked")
    approval = request_approval(
        session,
        access,
        organization_id=plan.organization_id,
        project_id=plan.project_id,
        action=ProtectedAction.DEPLOYMENT_STAGING,
        resource_type="deployment_plan",
        resource_id=plan.id,
        target_version=1,
        reason="Staging deployment plan approval",
        expires_at=None,
        request_id=request_id,
        plan_checksum=plan.plan_sha256,
    )
    plan.approval_id = approval.id
    plan.status = "approval_requested"
    record_audit_log(
        session,
        organization_id=plan.organization_id,
        actor_user_id=access.user.id,
        action="deployment.plan.approval_requested",
        resource_type="deployment_plan",
        resource_id=plan.id,
        approval_id=approval.id,
        correlation_id=plan.id,
        request_id=request_id,
        after={"plan_sha256": plan.plan_sha256},
        result="success",
    )
    return approval


def evaluate_staging_plan(
    session: Session,
    access: OrganizationAccess,
    plan: DeploymentPlan,
    *,
    current_plan_sha256: str,
    current_state_identity: str,
    current_account_id: str,
    current_region: str,
    request_id: uuid.UUID,
) -> ExecutionDecision:
    reason: str | None = None
    if plan.organization_id != access.membership.organization_id:
        reason = "CROSS_TENANT"
    elif plan.environment != "staging" or plan.target_environment != "staging":
        reason = "WRONG_ENVIRONMENT"
    elif plan.status == "superseded":
        reason = "PLAN_SUPERSEDED"
    elif plan.security_gate_status == GATE_BLOCKED:
        reason = "SECURITY_GATE_BLOCKED"
    elif plan.security_gate_status == "not_checked":
        reason = "SECURITY_GATE_NOT_CHECKED"
    elif plan.aws_account_id != current_account_id:
        reason = "WRONG_ACCOUNT"
    elif plan.aws_region != current_region:
        reason = "WRONG_REGION"
    elif (
        not plan.terraform_state_identity
        or plan.terraform_state_identity != current_state_identity
    ):
        reason = "WRONG_STATE"
    elif plan.plan_sha256 != current_plan_sha256:
        reason = "PLAN_CHECKSUM_MISMATCH"
    approval = (
        session.get(ProtectedApproval, plan.approval_id) if plan.approval_id else None
    )
    if reason is None and (approval is None or approval.status != "approved"):
        reason = "APPROVAL_MISSING"
    if reason is None and approval and approval.plan_checksum != current_plan_sha256:
        reason = "PLAN_CHECKSUM_MISMATCH"
    if reason is None and approval and approval.resource_id != plan.id:
        reason = "APPROVAL_TARGET_MISMATCH"
    if (
        reason is None
        and approval
        and approval.expires_at
        and approval.expires_at <= datetime.now(timezone.utc)
    ):
        reason = "APPROVAL_STALE"
    if (
        reason is None
        and approval
        and approval.requires_distinct_approver
        and approval.requested_by_user_id == approval.decided_by_user_id
    ):
        reason = "FOUR_EYES_REQUIRED"
    try:
        if reason is None:
            require_permission(
                session,
                access,
                Permission.DEPLOYMENT_EXECUTE_AUTHORIZE,
                plan.project_id,
            )
    except HTTPException:
        reason = "PERMISSION_DENIED"
    allowed = reason is None
    record_audit_log(
        session,
        organization_id=plan.organization_id,
        actor_user_id=access.user.id,
        action="deployment.plan.execution_authorized"
        if allowed
        else "deployment.plan.execution_denied",
        resource_type="deployment_plan",
        resource_id=plan.id,
        approval_id=approval.id if approval else None,
        correlation_id=plan.id,
        request_id=request_id,
        after={"plan_sha256": current_plan_sha256, "environment": plan.environment},
        result="authorized" if allowed else "denied",
        reason=reason,
    )
    return ExecutionDecision(allowed, reason)


def can_execute_staging_plan(*args: Any, **kwargs: Any) -> bool:
    return evaluate_staging_plan(*args, **kwargs).allowed
