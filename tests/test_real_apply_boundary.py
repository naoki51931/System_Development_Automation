import uuid
from datetime import datetime, timedelta, timezone
import inspect
from pathlib import Path

import pytest

from app.services.real_apply_boundary import (
    EXPECTED_ACCOUNT_ID,
    EXPECTED_REGION,
    EXPECTED_RUNTIME_STATE_KEY,
    EXPECTED_STATE_BUCKET,
    DisabledAwsIdentityVerifier,
    DisabledTerraformApplyExecutor,
    FakeAwsIdentityVerifier,
    IdentityBinding,
    IdentityVerificationUnavailable,
    VerifiedSavedPlanPath,
    build_staging_saved_plan_apply_argv,
    evaluate_real_apply_preflight,
    identity_binding_reasons,
    revalidate_saved_plan_path,
)


def binding() -> IdentityBinding:
    return IdentityBinding(
        organization_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        deployment_plan_id=uuid.uuid4(),
        deployment_plan_sha256="a" * 64,
        saved_plan_sha256="b" * 64,
        terraform_root="environment/staging",
        state_bucket=EXPECTED_STATE_BUCKET,
        state_key=EXPECTED_RUNTIME_STATE_KEY,
        region=EXPECTED_REGION,
    )


def test_fake_verifier_creates_server_side_bound_evidence():
    now = datetime.now(timezone.utc)
    current = binding()
    evidence = FakeAwsIdentityVerifier().verify(binding=current, now=now)
    assert evidence.account_id == EXPECTED_ACCOUNT_ID
    assert evidence.deployment_plan_id == current.deployment_plan_id
    assert identity_binding_reasons(evidence, current, now=now) == ()
    assert "secret" not in evidence.sanitized_dict()


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("account_id", "999999999999", "WRONG_AWS_ACCOUNT"),
        ("region", "us-east-1", "WRONG_AWS_REGION"),
        ("state_bucket", "other-bucket", "WRONG_STATE_BUCKET"),
        ("state_key", "cloud-a/prod/terraform.tfstate", "WRONG_STATE_KEY"),
        ("terraform_root", "environment", "WRONG_TERRAFORM_ROOT"),
        ("deployment_plan_sha256", "c" * 64, "PLAN_CHECKSUM_MISMATCH"),
        ("saved_plan_sha256", "d" * 64, "SAVED_PLAN_CHECKSUM_MISMATCH"),
    ],
)
def test_identity_binding_rejects_drift(field, value, reason):
    now = datetime.now(timezone.utc)
    current = binding()
    evidence = FakeAwsIdentityVerifier().verify(binding=current, now=now)
    changed = evidence.__class__(**{**evidence.__dict__, field: value})
    assert reason in identity_binding_reasons(changed, current, now=now)


def test_identity_evidence_expiry_blocks():
    current = binding()
    verified_at = datetime.now(timezone.utc) - timedelta(minutes=11)
    evidence = FakeAwsIdentityVerifier().verify(binding=current, now=verified_at)
    assert "AWS_IDENTITY_EVIDENCE_EXPIRED" in identity_binding_reasons(
        evidence, current, now=datetime.now(timezone.utc)
    )


def test_valid_identity_is_ready_but_disabled_and_authorization_is_required():
    now = datetime.now(timezone.utc)
    current = binding()
    evidence = FakeAwsIdentityVerifier().verify(binding=current, now=now)
    ready = evaluate_real_apply_preflight(
        evidence, current, authorization_ready=True, now=now
    )
    assert ready.status == "READY_BUT_DISABLED"
    assert "REAL_TERRAFORM_APPLY_DISABLED" in ready.reason_codes
    blocked = evaluate_real_apply_preflight(
        evidence, current, authorization_ready=False, now=now
    )
    assert blocked.status == "BLOCKED"
    assert "EXECUTION_AUTHORIZATION_REQUIRED" in blocked.reason_codes


def test_production_identity_and_missing_evidence_block():
    current = binding()
    production = FakeAwsIdentityVerifier().verify(
        binding=current, now=datetime.now(timezone.utc)
    )
    production = production.__class__(
        **{**production.__dict__, "environment": "production"}
    )
    result = evaluate_real_apply_preflight(
        production, current, authorization_ready=True
    )
    assert result.status == "BLOCKED"
    assert "WRONG_ENVIRONMENT" in result.reason_codes
    assert (
        evaluate_real_apply_preflight(None, current, authorization_ready=True).status
        == "BLOCKED"
    )


def test_disabled_verifier_and_executor_fail_closed():
    with pytest.raises(IdentityVerificationUnavailable):
        DisabledAwsIdentityVerifier().verify(
            binding=binding(), now=datetime.now(timezone.utc)
        )
    with pytest.raises(RuntimeError, match="REAL_TERRAFORM_APPLY_DISABLED"):
        DisabledTerraformApplyExecutor().execute()
    assert "subprocess" not in inspect.getsource(DisabledTerraformApplyExecutor)


def test_fixed_argv_accepts_only_verified_saved_plan_path():
    argv = build_staging_saved_plan_apply_argv(
        VerifiedSavedPlanPath(Path("/trusted/approved.tfplan"))
    )
    assert argv == ("terraform", "apply", "/trusted/approved.tfplan")
    with pytest.raises(TypeError):
        build_staging_saved_plan_apply_argv(Path("/trusted/approved.tfplan"))


def test_execution_time_saved_plan_rehash_rejects_mutation_and_traversal(tmp_path):
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    path = trusted / "approved.tfplan"
    path.write_bytes(b"approved")
    import hashlib

    digest = hashlib.sha256(b"approved").hexdigest()
    stat = path.stat()
    assert revalidate_saved_plan_path(
        path,
        trusted_root=trusted,
        expected_sha256=digest,
        expected_device=stat.st_dev,
        expected_inode=stat.st_ino,
        expected_size=stat.st_size,
    )
    path.write_bytes(b"mutated")
    assert not revalidate_saved_plan_path(
        path, trusted_root=trusted, expected_sha256=digest
    )
    outside = tmp_path / "outside.tfplan"
    outside.write_bytes(b"approved")
    assert not revalidate_saved_plan_path(
        outside, trusted_root=trusted, expected_sha256=digest
    )
