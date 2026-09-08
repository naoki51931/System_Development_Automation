"""Fail-closed foundation for a future real staging Terraform apply.

This module creates and validates server-side identity evidence, but it never
calls AWS, Terraform, a backend, or a subprocess.  The production verifier is
deliberately disabled until a separately approved read-only AWS verifier exists.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
from typing import Protocol

from app.services.terraform_executor import ExecutionEnvironmentContext

EXPECTED_ACCOUNT_ID = "557604519341"
EXPECTED_REGION = "eu-west-2"
EXPECTED_STATE_BUCKET = "ai-platform-terraform-state-557604519341"
EXPECTED_RUNTIME_STATE_KEY = "system-navigator/staging/terraform.tfstate"
EXPECTED_ENVIRONMENT = "staging"
IDENTITY_EVIDENCE_TTL = timedelta(minutes=10)
FIXED_TERRAFORM_BINARY = "terraform"


class IdentityVerificationUnavailable(RuntimeError):
    """Raised when production AWS identity verification is not configured."""


@dataclass(frozen=True)
class AwsIdentityEvidence:
    account_id: str
    caller_arn: str
    region: str
    verified_at: datetime
    state_bucket: str
    state_key: str
    backend_region: str
    terraform_root: str
    deployment_plan_id: uuid.UUID
    deployment_plan_sha256: str
    saved_plan_sha256: str
    organization_id: uuid.UUID
    project_id: uuid.UUID
    environment: str
    verification_status: str
    credential_source_type: str = "unknown"

    def is_fresh(
        self, *, now: datetime | None = None, ttl: timedelta = IDENTITY_EVIDENCE_TTL
    ) -> bool:
        current = now or datetime.now(timezone.utc)
        verified = self.verified_at
        if verified.tzinfo is None:
            verified = verified.replace(tzinfo=timezone.utc)
        age = current - verified
        return timedelta(0) <= age <= ttl

    def sanitized_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["verified_at"] = self.verified_at.isoformat()
        result["deployment_plan_id"] = str(self.deployment_plan_id)
        result["organization_id"] = str(self.organization_id)
        result["project_id"] = str(self.project_id)
        return result


@dataclass(frozen=True)
class IdentityBinding:
    organization_id: uuid.UUID
    project_id: uuid.UUID
    deployment_plan_id: uuid.UUID
    deployment_plan_sha256: str
    saved_plan_sha256: str
    terraform_root: str
    state_bucket: str
    state_key: str
    region: str
    environment: str = EXPECTED_ENVIRONMENT


class AwsIdentityVerifier(Protocol):
    def verify(
        self, *, binding: IdentityBinding, now: datetime
    ) -> AwsIdentityEvidence: ...


class DisabledAwsIdentityVerifier:
    """Production default; real AWS identity verification is not enabled."""

    def verify(
        self, *, binding: IdentityBinding | None, now: datetime
    ) -> AwsIdentityEvidence:
        raise IdentityVerificationUnavailable("AWS identity verifier is disabled")


class FakeAwsIdentityVerifier:
    """Test-only server-side evidence issuer; it accepts no client payload."""

    def __init__(
        self,
        *,
        account_id: str = EXPECTED_ACCOUNT_ID,
        caller_arn: str = "arn:aws:iam::557604519341:role/test-read-only",
        region: str = EXPECTED_REGION,
        credential_source_type: str = "test-fixture",
    ) -> None:
        self.account_id = account_id
        self.caller_arn = caller_arn
        self.region = region
        self.credential_source_type = credential_source_type

    def verify(self, *, binding: IdentityBinding, now: datetime) -> AwsIdentityEvidence:
        return AwsIdentityEvidence(
            account_id=self.account_id,
            caller_arn=self.caller_arn,
            region=self.region,
            verified_at=now,
            state_bucket=binding.state_bucket,
            state_key=binding.state_key,
            backend_region=self.region,
            terraform_root=binding.terraform_root,
            deployment_plan_id=binding.deployment_plan_id,
            deployment_plan_sha256=binding.deployment_plan_sha256,
            saved_plan_sha256=binding.saved_plan_sha256,
            organization_id=binding.organization_id,
            project_id=binding.project_id,
            environment=binding.environment,
            verification_status="verified",
            credential_source_type=self.credential_source_type,
        )


def identity_binding_reasons(
    evidence: AwsIdentityEvidence,
    binding: IdentityBinding,
    *,
    now: datetime | None = None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if evidence.verification_status != "verified":
        reasons.append("AWS_IDENTITY_NOT_VERIFIED")
    if not evidence.is_fresh(now=now):
        reasons.append("AWS_IDENTITY_EVIDENCE_EXPIRED")
    if evidence.account_id != EXPECTED_ACCOUNT_ID:
        reasons.append("WRONG_AWS_ACCOUNT")
    if evidence.region != EXPECTED_REGION or evidence.backend_region != EXPECTED_REGION:
        reasons.append("WRONG_AWS_REGION")
    if evidence.state_bucket != EXPECTED_STATE_BUCKET:
        reasons.append("WRONG_STATE_BUCKET")
    if evidence.state_key != EXPECTED_RUNTIME_STATE_KEY:
        reasons.append("WRONG_STATE_KEY")
    if evidence.environment != EXPECTED_ENVIRONMENT:
        reasons.append("WRONG_ENVIRONMENT")
    if evidence.organization_id != binding.organization_id:
        reasons.append("CROSS_TENANT_EVIDENCE")
    if evidence.project_id != binding.project_id:
        reasons.append("WRONG_PROJECT_EVIDENCE")
    if evidence.deployment_plan_id != binding.deployment_plan_id:
        reasons.append("WRONG_PLAN_EVIDENCE")
    if evidence.deployment_plan_sha256 != binding.deployment_plan_sha256:
        reasons.append("PLAN_CHECKSUM_MISMATCH")
    if evidence.saved_plan_sha256 != binding.saved_plan_sha256:
        reasons.append("SAVED_PLAN_CHECKSUM_MISMATCH")
    if evidence.terraform_root != binding.terraform_root:
        reasons.append("WRONG_TERRAFORM_ROOT")
    if evidence.state_bucket != binding.state_bucket:
        reasons.append("STATE_BUCKET_BINDING_MISMATCH")
    if evidence.state_key != binding.state_key:
        reasons.append("STATE_KEY_BINDING_MISMATCH")
    if evidence.region != binding.region:
        reasons.append("REGION_BINDING_MISMATCH")
    if evidence.environment != binding.environment:
        reasons.append("ENVIRONMENT_BINDING_MISMATCH")
    return tuple(dict.fromkeys(reasons))


@dataclass(frozen=True)
class VerifiedSavedPlanPath:
    """Opaque path produced by a server-side saved-plan verifier."""

    path: Path


def revalidate_saved_plan_path(
    path: Path,
    *,
    trusted_root: Path,
    expected_sha256: str,
    expected_device: int | None = None,
    expected_inode: int | None = None,
    expected_size: int | None = None,
) -> bool:
    """Rehash an exact saved plan without opening Terraform or a backend."""

    if path.is_symlink() or not path.is_file():
        return False
    root = trusted_root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return False
    if not os.path.isfile(resolved):
        return False
    stat = resolved.stat()
    if expected_device is not None and stat.st_dev != expected_device:
        return False
    if expected_inode is not None and stat.st_ino != expected_inode:
        return False
    if expected_size is not None and stat.st_size != expected_size:
        return False
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected_sha256


def build_staging_saved_plan_apply_argv(
    verified_saved_plan: VerifiedSavedPlanPath,
) -> tuple[str, str, str]:
    """Build the only future apply argv; this function never executes it."""

    if not isinstance(verified_saved_plan, VerifiedSavedPlanPath):
        raise TypeError("only a server-verified saved plan path is accepted")
    path = verified_saved_plan.path
    if not path.is_absolute() or not path.name:
        raise ValueError("verified saved plan must be an absolute file path")
    return (FIXED_TERRAFORM_BINARY, "apply", str(path))


class DisabledTerraformApplyExecutor:
    """Tripwire executor: real Terraform apply is unavailable in this phase."""

    def execute(self, *_args: object, **_kwargs: object) -> None:
        raise RuntimeError("REAL_TERRAFORM_APPLY_DISABLED")


@dataclass(frozen=True)
class RealApplyPreflightResult:
    status: str
    reason_codes: tuple[str, ...]
    executor_type: str = "disabled_real_apply"


def evaluate_real_apply_preflight(
    evidence: AwsIdentityEvidence | None,
    binding: IdentityBinding,
    *,
    authorization_ready: bool,
    executor_enabled: bool = False,
    now: datetime | None = None,
) -> RealApplyPreflightResult:
    reasons = (
        list(identity_binding_reasons(evidence, binding, now=now))
        if evidence
        else ["AWS_IDENTITY_EVIDENCE_MISSING"]
    )
    if not authorization_ready:
        reasons.append("EXECUTION_AUTHORIZATION_REQUIRED")
    reasons = list(dict.fromkeys(reasons))
    if reasons:
        return RealApplyPreflightResult("BLOCKED", tuple(reasons))
    if not executor_enabled:
        return RealApplyPreflightResult(
            "READY_BUT_DISABLED", ("REAL_TERRAFORM_APPLY_DISABLED",)
        )
    return RealApplyPreflightResult("READY_BUT_DISABLED", ())


def build_identity_binding(
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    deployment_plan_id: uuid.UUID,
    deployment_plan_sha256: str,
    saved_plan_sha256: str,
    context: ExecutionEnvironmentContext,
) -> IdentityBinding:
    return IdentityBinding(
        organization_id=organization_id,
        project_id=project_id,
        deployment_plan_id=deployment_plan_id,
        deployment_plan_sha256=deployment_plan_sha256,
        saved_plan_sha256=saved_plan_sha256,
        terraform_root=context.terraform_root or "",
        state_bucket=context.state_bucket or "",
        state_key=context.state_key or "",
        region=context.aws_region or "",
        environment=context.environment or "",
    )
