"""Fake-only saved-plan execution boundary.

This module exercises the execution-time security checks without starting
Terraform, invoking AWS, or mutating the filesystem.  It deliberately accepts
an already verified saved-plan evidence object rather than a command or raw
Terraform arguments.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit_log
from app.auth.dependencies import OrganizationAccess
from app.auth.permissions import Permission, require_permission
from app.models import DeploymentExecution, DeploymentPlan
from app.services.terraform_cli import SavedPlanVerification
from app.services.terraform_executor import (
    ExecutionEnvironmentContext,
    SafeStagingTerraformExecutor,
)

FakeOutcome = Literal["success", "failure", "timeout", "cancel", "unknown"]


@dataclass(frozen=True)
class ApprovedSavedPlan:
    """Server-resolved handle for the exact plan file under verification."""

    path: Path
    verification: SavedPlanVerification


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FakeTerraformApplyExecutor:
    """Simulate apply outcomes after complete execution-time revalidation."""

    def __init__(
        self,
        preparation: SafeStagingTerraformExecutor,
        *,
        trusted_plan_root: Path,
    ) -> None:
        self.preparation = preparation
        self.trusted_plan_root = trusted_plan_root.resolve()
        if not self.trusted_plan_root.is_dir():
            raise ValueError("trusted plan root must be an existing directory")

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
            actor_type="human",
            action=action,
            resource_type="deployment_execution",
            resource_id=execution.id,
            approval_id=execution.approval_id,
            correlation_id=execution.correlation_id,
            request_id=request_id,
            result=result,
            reason=reason,
            after={
                "status": execution.status,
                "executor_type": "fake",
                "plan_sha256": execution.plan_sha256,
            },
        )

    def _blocked(
        self,
        session: Session,
        access: OrganizationAccess,
        execution: DeploymentExecution,
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

    def _saved_plan_ok(
        self, saved_plan: ApprovedSavedPlan
    ) -> tuple[str, os.stat_result] | None:
        path = saved_plan.path
        if path.is_symlink() or not path.is_file():
            return None
        resolved = path.resolve()
        try:
            resolved.relative_to(self.trusted_plan_root)
        except ValueError:
            return None
        stat = resolved.stat()
        if not os.path.isfile(resolved):
            return None
        if saved_plan.verification.verification_status != "succeeded":
            return None
        before = saved_plan.verification.saved_plan_file_sha256_before
        after = saved_plan.verification.saved_plan_file_sha256_after
        current = _sha256(resolved)
        if not before or before != after or current != before:
            return None
        return current, stat

    def _evidence(
        self,
        execution: DeploymentExecution,
        plan: DeploymentPlan,
        context: ExecutionEnvironmentContext,
        saved_sha: str,
        result: str,
        reason: str | None,
        started_at: datetime,
        finished_at: datetime,
    ) -> dict[str, object]:
        evidence: dict[str, object] = {
            "executor_type": "fake",
            "execution_id": str(execution.id),
            "deployment_plan_id": str(plan.id),
            "approval_id": str(execution.approval_id),
            "organization_id": str(execution.organization_id),
            "project_id": str(execution.project_id),
            "environment": context.environment,
            "artifact_sha256": plan.plan_sha256,
            "plan_sha256": plan.plan_sha256,
            "saved_plan_sha256": saved_sha,
            "expected_account": context.aws_account_id,
            "expected_region": context.aws_region,
            "state_identity": context.state_identity,
            "terraform_root": context.terraform_root,
            "actor": str(execution.requested_by),
            "actor_type": "human",
            "result": result,
            "reason": reason,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "correlation_id": str(execution.correlation_id),
        }
        evidence_bytes = json.dumps(
            evidence, sort_keys=True, separators=(",", ":")
        ).encode()
        evidence["execution_evidence_sha256"] = hashlib.sha256(
            evidence_bytes
        ).hexdigest()
        return evidence

    def execute(
        self,
        session: Session,
        access: OrganizationAccess,
        execution: DeploymentExecution,
        *,
        context: ExecutionEnvironmentContext,
        saved_plan: ApprovedSavedPlan,
        request_id: uuid.UUID,
        outcome: FakeOutcome = "success",
        actor_type: str = "human",
    ) -> DeploymentExecution:
        if execution.organization_id != access.membership.organization_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant access denied")
        require_permission(
            session, access, Permission.DEPLOYMENT_EXECUTE, execution.project_id
        )
        if (
            actor_type == "ai_agent"
            or getattr(access.user, "actor_type", "human") == "ai_agent"
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "AI_AGENT cannot execute")
        locked_execution = session.scalar(
            select(DeploymentExecution)
            .where(DeploymentExecution.id == execution.id)
            .with_for_update()
        )
        if locked_execution is None:
            return self._blocked(
                session, access, execution, "EXECUTION_NOT_FOUND", request_id
            )
        execution = locked_execution
        if execution.status in {"executed", "failed", "blocked"}:
            return execution
        if execution.status != "prepared":
            return self._blocked(
                session, access, execution, "INVALID_LIFECYCLE", request_id
            )
        checked = self._saved_plan_ok(saved_plan)
        if checked is None:
            return self._blocked(
                session,
                access,
                execution,
                "EXECUTION_PLAN_CHECKSUM_MISMATCH",
                request_id,
            )
        saved_sha, before_stat = checked
        self._audit(
            session,
            execution,
            access,
            "deployment.execution.revalidation_started",
            "started",
            request_id,
        )
        revalidated = self.preparation.authorize(
            session,
            access,
            execution,
            context=context,
            request_id=request_id,
            actor_type=actor_type,
            force_revalidate=True,
        )
        if revalidated.status != "authorized":
            return revalidated
        plan = session.get(DeploymentPlan, execution.deployment_plan_id)
        if plan is None:
            return self._blocked(
                session, access, execution, "PLAN_NOT_FOUND", request_id
            )
        after_path = saved_plan.path.resolve()
        if (
            saved_plan.path.is_symlink()
            or not after_path.is_file()
            or _sha256(after_path) != saved_sha
            or (
                before_stat.st_dev,
                before_stat.st_ino,
                before_stat.st_size,
            )
            != (
                after_path.stat().st_dev,
                after_path.stat().st_ino,
                after_path.stat().st_size,
            )
        ):
            return self._blocked(
                session,
                access,
                execution,
                "EXECUTION_PLAN_CHECKSUM_MISMATCH",
                request_id,
            )
        started_at = datetime.now(timezone.utc)
        if outcome == "unknown":
            result, reason = "blocked", "UNKNOWN_OUTCOME"
        elif outcome == "success":
            result, reason = "success", None
        elif outcome == "timeout":
            result, reason = "failed", "EXECUTION_TIMEOUT"
        elif outcome == "cancel":
            result, reason = "failed", "EXECUTION_CANCELLED"
        else:
            result, reason = "failed", "FAKE_EXECUTION_FAILED"
        execution.status = "executed" if result == "success" else "failed"
        if result == "blocked":
            execution.status = "blocked"
        execution.authorization_result = "FAKE_EXECUTION_" + result.upper()
        execution.authorization_reason = reason
        finished_at = datetime.now(timezone.utc)
        execution.executed_at = finished_at
        execution.evidence = self._evidence(
            execution, plan, context, saved_sha, result, reason, started_at, finished_at
        )
        self._audit(
            session,
            execution,
            access,
            "deployment.execution." + result,
            result,
            request_id,
            reason,
        )
        return execution
