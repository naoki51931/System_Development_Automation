"""Production attestation tests.

The deterministic private seed below is TEST ONLY / NOT FOR PRODUCTION.  The
Production private key belongs in a protected signer (GitHub Environment secret
or AWS KMS) and is never stored in this repository.
"""

import base64
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts.verify_production_migration_attestation import (
    ATTESTATION_PAYLOAD_FIELDS,
    VerificationError,
    canonical_json,
    load_json,
    parse_args,
    validate_artifact,
)

TEST_ONLY_PRIVATE_SEED = bytes(range(32))
TEST_TRUST = Path(__file__).parent / "fixtures/production_attestation_test_trust.json"
NOW = datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc)
RELEASE_SHA = "b" * 40
DIGEST = "a" * 64
TASK = "arn:aws:ecs:eu-west-2:557604519341:task/ai-platform-prod/1234567890abcdef1234567890abcdef"
TASK_DEFINITION = (
    "arn:aws:ecs:eu-west-2:557604519341:task-definition/ai-platform-prod-migration:7"
)


def evidence(**updates):
    value = {
        "schema_version": 1,
        "release_sha": RELEASE_SHA,
        "aws_account_id": "557604519341",
        "aws_region": "eu-west-2",
        "verification_task_arn": TASK,
        "verification_task_definition_arn": TASK_DEFINITION,
        "exit_code": 0,
        "expected_alembic_head": "8d4f2a7c9b11",
        "observed_alembic_head": "8d4f2a7c9b11",
        "verified_at": "2026-08-15T00:00:00Z",
        "output_sha256": "c" * 64,
        "github_repository": "naoki51931/System_Development_Automation",
        "github_workflow": "production-release",
        "github_job": "production-plan",
        "github_ref": "refs/heads/master",
        "github_run_id": 123,
        "github_run_attempt": 1,
    }
    value.update(updates)
    return value


def artifact(ev=None, **updates):
    ev = ev or evidence()
    value = {
        "schema_version": 2,
        "release_sha": RELEASE_SHA,
        "aws_account_id": "557604519341",
        "aws_region": "eu-west-2",
        "ecs_cluster_arn": "arn:aws:ecs:eu-west-2:557604519341:cluster/ai-platform-prod",
        "migration_task_arn": TASK,
        "migration_task_definition_arn": TASK_DEFINITION,
        "migration_task_definition_revision": 7,
        "app_image_uri": f"557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod@sha256:{DIGEST}",
        "resolved_image_digest": f"sha256:{DIGEST}",
        "container_name": "migration",
        "exit_code": 0,
        "stopped_reason": "Essential container exited",
        "expected_alembic_head": "8d4f2a7c9b11",
        "verified_alembic_head": "8d4f2a7c9b11",
        "verified_at": "2026-08-15T00:00:00Z",
        "github_repository": "naoki51931/System_Development_Automation",
        "github_workflow": "production-release",
        "github_run_id": 123,
        "github_run_attempt": 1,
        "github_job": "production-plan",
        "github_sha": RELEASE_SHA,
        "github_ref": "refs/heads/master",
        "signature_algorithm": "Ed25519",
        "signing_key_id": "production-release-2026-01",
        "alembic_evidence_sha256": hashlib.sha256(canonical_json(ev)).hexdigest(),
    }
    value.update(updates)
    payload = canonical_json({key: value[key] for key in ATTESTATION_PAYLOAD_FIELDS})
    value["artifact_sha256"] = hashlib.sha256(payload).hexdigest()
    value["artifact_signature"] = base64.b64encode(
        Ed25519PrivateKey.from_private_bytes(TEST_ONLY_PRIVATE_SEED).sign(payload)
    ).decode()
    return value


def validate(value=None, ev=None):
    ev = ev or evidence()
    return validate_artifact(
        value or artifact(ev),
        approved_release_sha=RELEASE_SHA,
        alembic_evidence=ev,
        trust_config_path=TEST_TRUST,
        now=NOW,
    )


def test_approved_repository_trust_root_and_bound_evidence_pass():
    assert validate()["signing_key_id"] == "production-release-2026-01"


@pytest.mark.parametrize(
    "change",
    [
        {"signing_key_id": "attacker-key"},
        {"signature_algorithm": "RSA"},
        {"github_repository": "attacker/repository"},
        {"github_job": "attacker-job"},
        {"release_sha": "d" * 40},
    ],
)
def test_unknown_identity_algorithm_and_release_fail(change):
    with pytest.raises(VerificationError):
        validate(artifact(**change))


def test_attacker_generated_key_and_signature_fail():
    value = artifact()
    payload = canonical_json({key: value[key] for key in ATTESTATION_PAYLOAD_FIELDS})
    value["artifact_signature"] = base64.b64encode(
        Ed25519PrivateKey.generate().sign(payload)
    ).decode()
    with pytest.raises(VerificationError, match="signature"):
        validate(value)


def test_artifact_key_substitution_and_cli_override_are_impossible():
    with pytest.raises(VerificationError, match="exactly"):
        validate(artifact(public_key_b64="attacker"))
    with pytest.raises(SystemExit):
        parse_args(["--public-key-b64", "attacker"])
    with pytest.raises(SystemExit):
        parse_args(["--signing-key-id", "attacker"])


@pytest.mark.parametrize(
    "ev_change",
    [
        {"observed_alembic_head": "wrong"},
        {"exit_code": 1},
        {"release_sha": "d" * 40},
        {"github_run_id": 0},
        {"github_ref": "refs/heads/feature"},
        {"verified_at": "2026-08-13T00:00:00Z"},
    ],
)
def test_forged_alembic_provenance_fails(ev_change):
    ev = evidence(**ev_change)
    with pytest.raises(VerificationError):
        validate(artifact(ev), ev)


def test_specific_alembic_evidence_is_cryptographically_bound():
    signed_for = evidence()
    substituted = evidence(output_sha256="d" * 64)
    with pytest.raises(VerificationError, match="binding"):
        validate(artifact(signed_for), substituted)


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("artifact", "extra", "x"),
        ("artifact", "stopped_reason", None),
        ("artifact", "exit_code", 0.0),
        ("evidence", "extra", "x"),
        ("evidence", "output_sha256", None),
        ("evidence", "exit_code", 0.0),
    ],
)
def test_schemas_are_closed_non_null_and_strictly_typed(target, field, value):
    ev = evidence()
    att = artifact(ev)
    (att if target == "artifact" else ev)[field] = value
    with pytest.raises(VerificationError):
        validate(att, ev)


def test_loader_rejects_duplicate_fields_and_non_finite_numbers(tmp_path):
    for raw in ('{"schema_version":1,"schema_version":1}', '{"value":NaN}'):
        path = tmp_path / "input.json"
        path.write_text(raw, encoding="utf-8")
        with pytest.raises(VerificationError):
            load_json(path)


def test_canonical_vectors_are_platform_stable():
    vectors = [
        (
            {"ascii": "release", "count": 1},
            "d15083eea4203aba38b43010fad3a6e59598f66ca3de257a56bd7fee3bf5f0ba",
        ),
        (
            {"nested": {"a": True, "z": [1, 2]}, "schema": 2},
            "12d0708e6c804fcba24083c9411453de5737f81abf03efd00b7076a563dda535",
        ),
    ]
    for value, expected_sha in vectors:
        assert hashlib.sha256(canonical_json(value)).hexdigest() == expected_sha


def test_non_ascii_schema_value_is_rejected_before_canonicalization():
    with pytest.raises(VerificationError, match="invalid"):
        validate(artifact(stopped_reason="decomposed-e\u0301"))
