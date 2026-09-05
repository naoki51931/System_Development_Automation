"""Safe staging Terraform execution boundary.

This module validates and prepares an execution record only.  It never starts
Terraform and deliberately has no subprocess or AWS client dependency.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit_log
from app.auth.dependencies import OrganizationAccess
from app.auth.permissions import Permission, ProtectedAction, require_permission
from app.models import DeploymentExecution, DeploymentPlan, ProtectedApproval
from app.services.deployment import (
    GATE_BLOCKED,
    canonical_plan_bytes,
    check_security_gate,
    plan_sha256,
)
from app.services.storage import ArtifactStorage


@dataclass(frozen=True)
class ExecutionEnvironmentContext:
    aws_account_id: str | None
    aws_region: str | None
    terraform_root: str | None
    state_identity: str | None
    environment: str | None


class TerraformVersionProvider(Protocol):
    def metadata(self) -> dict[str, str]: ...


class NoopTerraformVersionProvider:
    def metadata(self) -> dict[str, str]:
        return {}


class TerraformCommandPolicy:
    """Read-only command names retained for documentation/tests only."""

    @staticmethod
    def version_argv() -> list[str]:
        return ["terraform", "version"]

    @staticmethod
    def show_argv() -> list[str]:
        return ["terraform", "show"]


class SafeStagingTerraformExecutor:
    def __init__(
        self,
        storage: ArtifactStorage,
        *,
        allowed_terraform_roots: frozenset[str] = frozenset({"environment/staging"}),
        repository_root: Path | None = None,
        version_provider: TerraformVersionProvider | None = None,
    ) -> None:
        self.storage = storage
        self.allowed_terraform_roots = allowed_terraform_roots
        self.repository_root = repository_root.resolve() if repository_root else None
        self.version_provider = version_provider or NoopTerraformVersionProvider()

    def _audit(
        self,
        session: Session,
        execution: DeploymentExecution,
        access: OrganizationAccess,
        action: str,
        result: str,
        request_id: uuid.UUID,
        reason: str | None = None,
    ) -> None:
        record_audit_log(
            session,
            organization_id=execution.organization_id,
            actor_user_id=access.user.id,
            action=action,
            resource_type="deployment_execution",
            resource_id=execution.id,
            approval_id=execution.approval_id,
            correlation_id=execution.correlation_id,
            request_id=request_id,
            result=result,
            reason=reason,
            after={"status": execution.status, "plan_sha256": execution.plan_sha256},
        )

    def request(
        self,
        session: Session,
        access: OrganizationAccess,
        plan: DeploymentPlan,
        *,
        context: ExecutionEnvironmentContext,
        request_id: uuid.UUID,
        actor_type: str = "human",
    ) -> DeploymentExecution:
        if plan.organization_id != access.membership.organization_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant access denied")
        require_permission(
            session, access, Permission.DEPLOYMENT_EXECUTE_AUTHORIZE, plan.project_id
        )
        if (
            actor_type == "ai_agent"
            or getattr(access.user, "actor_type", "human") == "ai_agent"
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "AI_AGENT cannot invoke executor"
            )
        if plan.approval_id is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Approved staging plan is required"
            )
        existing = session.scalar(
            select(DeploymentExecution)
            .where(
                DeploymentExecution.organization_id == plan.organization_id,
                DeploymentExecution.project_id == plan.project_id,
                DeploymentExecution.status.in_(
                    ("requested", "validating", "authorized", "prepared")
                ),
            )
            .order_by(DeploymentExecution.requested_at.desc())
        )
        if existing is not None:
            return existing
        execution = DeploymentExecution(
            organization_id=plan.organization_id,
            project_id=plan.project_id,
            deployment_plan_id=plan.id,
            approval_id=plan.approval_id,
            requested_by=access.user.id,
            plan_sha256=plan.plan_sha256,
            expected_account_id=context.aws_account_id or "",
            expected_region=context.aws_region or "",
            expected_state_identity=context.state_identity or "",
            expected_terraform_root=context.terraform_root or "",
            correlation_id=uuid.uuid4(),
        )
        session.add(execution)
        session.flush()
        self._audit(
            session,
            execution,
            access,
            "deployment.execution.requested",
            "success",
            request_id,
        )
        return execution

    def _artifact(
        self, plan: DeploymentPlan
    ) -> tuple[dict[str, Any] | None, str | None]:
        try:
            raw = self.storage.get_object(plan.plan_storage_key)
            document = json.loads(raw)
            if not isinstance(document, dict):
                return None, None
            return document, plan_sha256(canonical_plan_bytes(document))
        except (ValueError, TypeError, UnicodeDecodeError):
            return None, None

    def _root_ok(self, root: str | None) -> bool:
        if not root:
            return False
        pure = PurePosixPath(root)
        if (
            pure.is_absolute()
            or ".." in pure.parts
            or "\\" in root
            or str(pure) != root
        ):
            return False
        if root not in self.allowed_terraform_roots:
            return False
        if self.repository_root is not None:
            candidate = self.repository_root.joinpath(*pure.parts)
            for part in [
                self.repository_root,
                *candidate.relative_to(self.repository_root).parents,
                candidate,
            ]:
                if part.is_symlink():
                    return False
            resolved = candidate.resolve()
            if (
                self.repository_root not in resolved.parents
                and resolved != self.repository_root
            ):
                return False
        return True

    def _block(
        self,
        session: Session,
        execution: DeploymentExecution,
        access: OrganizationAccess,
        reason: str,
        request_id: uuid.UUID,
    ) -> DeploymentExecution:
        execution.status = "blocked"
        execution.authorization_result = "BLOCKED"
        execution.authorization_reason = reason
        self._audit(
            session,
            execution,
            access,
            "deployment.execution.blocked",
            "blocked",
            request_id,
            reason,
        )
        return execution

    def authorize(
        self,
        session: Session,
        access: OrganizationAccess,
        execution: DeploymentExecution,
        *,
        context: ExecutionEnvironmentContext,
        request_id: uuid.UUID,
        actor_type: str = "human",
        force_revalidate: bool = False,
    ) -> DeploymentExecution:
        if execution.organization_id != access.membership.organization_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant access denied")
        if execution.status in {"prepared", "executed"} and not force_revalidate:
            return execution
        if execution.status == "executed":
            return execution
        execution.status = "validating"
        self._audit(
            session,
            execution,
            access,
            "deployment.execution.validation_started",
            "started",
            request_id,
        )
        plan = session.get(DeploymentPlan, execution.deployment_plan_id)
        approval = session.get(ProtectedApproval, execution.approval_id)
        if plan is None or approval is None:
            return self._block(
                session, execution, access, "APPROVAL_MISSING", request_id
            )
        document, recomputed = self._artifact(plan)
        if (
            document is None
            or recomputed != plan.plan_sha256
            or recomputed != execution.plan_sha256
        ):
            return self._block(
                session, execution, access, "PLAN_CHECKSUM_MISMATCH", request_id
            )
        if (
            not context.aws_account_id
            or not context.aws_region
            or not context.terraform_root
            or not context.environment
        ):
            return self._block(
                session, execution, access, "UNKNOWN_EXECUTION_CONTEXT", request_id
            )
        if not context.state_identity:
            return self._block(
                session, execution, access, "STATE_IDENTITY_UNKNOWN", request_id
            )
        if (
            not self._root_ok(context.terraform_root)
            or context.terraform_root != plan.terraform_root
        ):
            return self._block(
                session, execution, access, "WRONG_TERRAFORM_ROOT", request_id
            )
        if (
            context.environment != "staging"
            or plan.environment != "staging"
            or plan.target_environment != "staging"
        ):
            return self._block(
                session, execution, access, "WRONG_ENVIRONMENT", request_id
            )
        if (
            not context.aws_account_id
            or context.aws_account_id != plan.aws_account_id
            or context.aws_account_id != execution.expected_account_id
        ):
            return self._block(session, execution, access, "WRONG_ACCOUNT", request_id)
        if (
            not context.aws_region
            or context.aws_region != plan.aws_region
            or context.aws_region != execution.expected_region
        ):
            return self._block(session, execution, access, "WRONG_REGION", request_id)
        if (
            not plan.terraform_state_identity
            or context.state_identity != plan.terraform_state_identity
            or context.state_identity != execution.expected_state_identity
        ):
            return self._block(
                session, execution, access, "STATE_IDENTITY_CHANGED", request_id
            )
        if plan.superseded_by_id is not None or plan.status == "superseded":
            return self._block(
                session, execution, access, "PLAN_SUPERSEDED", request_id
            )
        latest = session.scalar(
            select(DeploymentPlan)
            .where(
                DeploymentPlan.organization_id == plan.organization_id,
                DeploymentPlan.project_id == plan.project_id,
                DeploymentPlan.environment == "staging",
                DeploymentPlan.id != plan.id,
                DeploymentPlan.status.in_(
                    ("created", "security_checked", "approval_requested", "approved")
                ),
                DeploymentPlan.created_at > plan.created_at,
            )
            .limit(1)
        )
        if latest is not None:
            return self._block(
                session, execution, access, "PLAN_SUPERSEDED", request_id
            )
        gate = check_security_gate(
            plan,
            document,
            expected_account_id=context.aws_account_id,
            expected_region=context.aws_region,
            expected_root=context.terraform_root,
            expected_state_identity=context.state_identity,
        )
        if gate.status == GATE_BLOCKED:
            return self._block(
                session, execution, access, "SECURITY_GATE_BLOCKED", request_id
            )
        if (
            approval.organization_id != plan.organization_id
            or approval.project_id != plan.project_id
            or approval.resource_id != plan.id
            or approval.action != ProtectedAction.DEPLOYMENT_STAGING.value
            or approval.target_version != 1
        ):
            return self._block(
                session, execution, access, "APPROVAL_TARGET_MISMATCH", request_id
            )
        if approval.status != "approved":
            return self._block(
                session,
                execution,
                access,
                "APPROVAL_REJECTED"
                if approval.status == "rejected"
                else "APPROVAL_MISSING",
                request_id,
            )
        if approval.expires_at is not None and approval.expires_at <= datetime.now(
            timezone.utc
        ):
            return self._block(
                session, execution, access, "APPROVAL_EXPIRED", request_id
            )
        if approval.plan_checksum != recomputed:
            return self._block(
                session, execution, access, "PLAN_CHECKSUM_MISMATCH", request_id
            )
        if approval.requires_distinct_approver and (
            approval.decided_by_user_id is None
            or approval.decided_by_user_id == approval.requested_by_user_id
        ):
            return self._block(
                session, execution, access, "FOUR_EYES_REQUIRED", request_id
            )
        if (
            actor_type == "ai_agent"
            or getattr(access.user, "actor_type", "human") == "ai_agent"
        ):
            return self._block(
                session, execution, access, "AI_AGENT_DENIED", request_id
            )
        try:
            require_permission(
                session,
                access,
                Permission.DEPLOYMENT_EXECUTE_AUTHORIZE,
                plan.project_id,
            )
        except HTTPException:
            return self._block(
                session, execution, access, "PERMISSION_DENIED", request_id
            )
        execution.status = "authorized"
        execution.authorization_result = "AUTHORIZED_FOR_STAGING_EXECUTION"
        execution.authorization_reason = None
        self._audit(
            session,
            execution,
            access,
            "deployment.execution.authorized",
            "authorized",
            request_id,
        )
        return execution

    def prepare(
        self,
        session: Session,
        access: OrganizationAccess,
        execution: DeploymentExecution,
        *,
        context: ExecutionEnvironmentContext,
        request_id: uuid.UUID,
        actor_type: str = "human",
    ) -> DeploymentExecution:
        if execution.organization_id != access.membership.organization_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant access denied")
        if execution.status == "prepared":
            return execution
        execution = self.authorize(
            session,
            access,
            execution,
            context=context,
            request_id=request_id,
            actor_type=actor_type,
        )
        if execution.status != "authorized":
            return execution
        plan = session.get(DeploymentPlan, execution.deployment_plan_id)
        if plan is None:
            return self._block(session, execution, access, "PLAN_NOT_FOUND", request_id)
        _document, recomputed = self._artifact(plan)
        if recomputed != plan.plan_sha256 or recomputed != execution.plan_sha256:
            return self._block(
                session, execution, access, "PLAN_CHECKSUM_MISMATCH", request_id
            )
        execution.status = "prepared"
        execution.prepared_at = datetime.now(timezone.utc)
        execution.evidence = {
            "deployment_plan_id": str(plan.id),
            "plan_sha256": recomputed,
            "approval_id": str(execution.approval_id),
            "approver": str(
                session.get(ProtectedApproval, execution.approval_id).decided_by_user_id
            ),
            "requester": str(execution.requested_by),
            "account": context.aws_account_id,
            "region": context.aws_region,
            "environment": context.environment,
            "terraform_root": context.terraform_root,
            "state_identity": context.state_identity,
            "security_gate_result": "revalidated",
            "terraform_version": self.version_provider.metadata(),
            "prepared_at": execution.prepared_at.isoformat(),
        }
        self._audit(
            session,
            execution,
            access,
            "deployment.execution.prepared",
            "prepared",
            request_id,
        )
        return execution
