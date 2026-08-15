"""Fail-closed verifier for the Production migration release handoff.

The Production trust root is repository-reviewed configuration.  Neither the
public key nor its approved key id can be supplied by a workflow caller.
"""

import argparse
import base64
import binascii
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ACCOUNT = "557604519341"
REGION = "eu-west-2"
ALEMBIC_HEAD = "8d4f2a7c9b11"
WORKFLOW_REPOSITORY = "naoki51931/System_Development_Automation"
WORKFLOW_NAME = "production-release"
WORKFLOW_JOB = "production-plan"
WORKFLOW_REF = "refs/heads/master"
TRUST_CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "config/production_migration_attestation_trust.json"
)
MAX_ATTESTATION_AGE = timedelta(hours=24)
MAX_CLOCK_SKEW = timedelta(minutes=5)
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ASCII = re.compile(r"[\x20-\x7e]+\Z")
IMAGE = re.compile(
    rf"{ACCOUNT}\.dkr\.ecr\.{REGION}\.amazonaws\.com/"
    r"ai-platform-prod@sha256:[0-9a-f]{64}\Z"
)
TASK = re.compile(
    rf"arn:aws:ecs:{REGION}:{ACCOUNT}:task/ai-platform-prod/[0-9a-f]{{32}}\Z"
)
TASK_DEFINITION = re.compile(
    rf"arn:aws:ecs:{REGION}:{ACCOUNT}:task-definition/"
    r"ai-platform-prod-migration:[1-9][0-9]*\Z"
)

TRUST_FIELDS = {
    "schema_version",
    "algorithm",
    "approved_key_id",
    "public_key_b64",
    "github_repository",
    "github_workflow",
    "github_job",
    "github_ref",
}
ALEMBIC_FIELDS = {
    "schema_version",
    "release_sha",
    "aws_account_id",
    "aws_region",
    "verification_task_arn",
    "verification_task_definition_arn",
    "exit_code",
    "expected_alembic_head",
    "observed_alembic_head",
    "verified_at",
    "output_sha256",
    "github_repository",
    "github_workflow",
    "github_job",
    "github_ref",
    "github_run_id",
    "github_run_attempt",
}
ATTESTATION_PAYLOAD_FIELDS = {
    "schema_version",
    "release_sha",
    "aws_account_id",
    "aws_region",
    "ecs_cluster_arn",
    "migration_task_arn",
    "migration_task_definition_arn",
    "migration_task_definition_revision",
    "app_image_uri",
    "resolved_image_digest",
    "container_name",
    "exit_code",
    "stopped_reason",
    "expected_alembic_head",
    "verified_alembic_head",
    "verified_at",
    "github_repository",
    "github_workflow",
    "github_run_id",
    "github_run_attempt",
    "github_job",
    "github_sha",
    "github_ref",
    "signature_algorithm",
    "signing_key_id",
    "alembic_evidence_sha256",
}
ATTESTATION_FIELDS = ATTESTATION_PAYLOAD_FIELDS | {
    "artifact_sha256",
    "artifact_signature",
}


class VerificationError(RuntimeError):
    pass


def _require(condition, message):
    if not condition:
        raise VerificationError(message)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise VerificationError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_json(path):
    try:
        return json.loads(
            Path(path).read_text(encoding="utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                VerificationError(f"non-finite JSON number: {value}")
            ),
        )
    except VerificationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"invalid JSON: {path}") from exc


load_artifact = load_json


def _closed_object(value, fields, name):
    _require(isinstance(value, dict), f"{name} must be a JSON object")
    _require(set(value) == fields, f"{name} must have exactly the approved fields")
    _require(all(item is not None for item in value.values()), f"{name} contains null")


def _ascii(value, name):
    _require(isinstance(value, str) and ASCII.fullmatch(value), f"invalid {name}")
    _require(unicodedata.normalize("NFC", value) == value, f"non-NFC {name}")


def canonical_json(value):
    """Return deterministic NFC JSON bytes; all schema strings are ASCII."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _parse_timestamp(value, *, now):
    _ascii(value, "timestamp")
    _require(value.endswith("Z"), "timestamp must be RFC3339 UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise VerificationError("invalid verification timestamp") from exc
    _require(
        parsed.isoformat().replace("+00:00", "Z") == value, "non-canonical timestamp"
    )
    _require(parsed <= now + MAX_CLOCK_SKEW, "verification timestamp is in the future")
    _require(now - parsed <= MAX_ATTESTATION_AGE, "verification evidence is stale")
    return parsed


def load_trust_config(path=TRUST_CONFIG_PATH):
    config = load_json(path)
    _closed_object(config, TRUST_FIELDS, "trust config")
    _require(config["schema_version"] == 1, "unsupported trust schema")
    _require(config["algorithm"] == "Ed25519", "trust algorithm must be Ed25519")
    for field in TRUST_FIELDS - {"schema_version", "public_key_b64"}:
        _ascii(config[field], f"trust {field}")
    _require(config["approved_key_id"], "approved key id is required")
    _require(
        config["github_repository"] == WORKFLOW_REPOSITORY, "trust repository mismatch"
    )
    _require(config["github_workflow"] == WORKFLOW_NAME, "trust workflow mismatch")
    _require(config["github_job"] == WORKFLOW_JOB, "trust job mismatch")
    _require(config["github_ref"] == WORKFLOW_REF, "trust ref mismatch")
    try:
        key = base64.b64decode(config["public_key_b64"], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise VerificationError("invalid trust public key base64") from exc
    _require(len(key) == 32, "Ed25519 public key must be 32 bytes")
    return config, key


def validate_alembic_evidence(evidence, *, release_sha, now):
    _closed_object(evidence, ALEMBIC_FIELDS, "Alembic evidence")
    _require(evidence["schema_version"] == 1, "unsupported Alembic evidence schema")
    _require(evidence["release_sha"] == release_sha, "Alembic release SHA mismatch")
    _require(evidence["aws_account_id"] == ACCOUNT, "Alembic account mismatch")
    _require(evidence["aws_region"] == REGION, "Alembic region mismatch")
    _require(
        TASK.fullmatch(evidence["verification_task_arn"]),
        "invalid verification task ARN",
    )
    _require(
        TASK_DEFINITION.fullmatch(evidence["verification_task_definition_arn"]),
        "invalid verification task definition ARN",
    )
    _require(
        type(evidence["exit_code"]) is int and evidence["exit_code"] == 0,
        "Alembic verification failed",
    )
    _require(
        evidence["expected_alembic_head"] == ALEMBIC_HEAD, "unexpected Alembic head"
    )
    _require(evidence["observed_alembic_head"] == ALEMBIC_HEAD, "Alembic head mismatch")
    _require(
        SHA256.fullmatch(evidence["output_sha256"]), "invalid Alembic output checksum"
    )
    _require(
        evidence["github_repository"] == WORKFLOW_REPOSITORY,
        "Alembic repository mismatch",
    )
    _require(evidence["github_workflow"] == WORKFLOW_NAME, "Alembic workflow mismatch")
    _require(evidence["github_job"] == WORKFLOW_JOB, "Alembic job mismatch")
    _require(evidence["github_ref"] == WORKFLOW_REF, "Alembic ref mismatch")
    _require(
        type(evidence["github_run_id"]) is int and evidence["github_run_id"] > 0,
        "invalid run id",
    )
    _require(
        type(evidence["github_run_attempt"]) is int
        and evidence["github_run_attempt"] > 0,
        "invalid run attempt",
    )
    for field, value in evidence.items():
        if isinstance(value, str):
            _ascii(value, f"Alembic {field}")
    _parse_timestamp(evidence["verified_at"], now=now)
    return hashlib.sha256(canonical_json(evidence)).hexdigest()


def validate_artifact(
    artifact,
    *,
    approved_release_sha,
    alembic_evidence,
    trust_config_path=TRUST_CONFIG_PATH,
    now=None,
):
    current = now or datetime.now(timezone.utc)
    _closed_object(artifact, ATTESTATION_FIELDS, "attestation")
    _require(artifact["schema_version"] == 2, "unsupported attestation schema")
    _require(
        SHA40.fullmatch(approved_release_sha or ""), "invalid approved release SHA"
    )
    _require(
        artifact["release_sha"] == approved_release_sha, "artifact release SHA mismatch"
    )
    _require(artifact["github_sha"] == approved_release_sha, "workflow SHA mismatch")
    _require(artifact["aws_account_id"] == ACCOUNT, "artifact account mismatch")
    _require(artifact["aws_region"] == REGION, "artifact region mismatch")
    _require(
        artifact["github_repository"] == WORKFLOW_REPOSITORY,
        "artifact repository mismatch",
    )
    _require(artifact["github_workflow"] == WORKFLOW_NAME, "artifact workflow mismatch")
    _require(artifact["github_job"] == WORKFLOW_JOB, "artifact job mismatch")
    _require(artifact["github_ref"] == WORKFLOW_REF, "artifact ref mismatch")
    _require(IMAGE.fullmatch(artifact["app_image_uri"]), "invalid Production image URI")
    _require(
        artifact["resolved_image_digest"] == artifact["app_image_uri"].split("@", 1)[1],
        "image digest mismatch",
    )
    _require(
        TASK.fullmatch(artifact["migration_task_arn"]), "invalid migration task ARN"
    )
    _require(
        TASK_DEFINITION.fullmatch(artifact["migration_task_definition_arn"]),
        "invalid task definition ARN",
    )
    _require(
        type(artifact["migration_task_definition_revision"]) is int
        and artifact["migration_task_definition_revision"] > 0,
        "invalid task revision",
    )
    _require(
        artifact["ecs_cluster_arn"]
        == f"arn:aws:ecs:{REGION}:{ACCOUNT}:cluster/ai-platform-prod",
        "cluster mismatch",
    )
    _require(artifact["container_name"] == "migration", "container mismatch")
    _require(
        type(artifact["exit_code"]) is int and artifact["exit_code"] == 0,
        "migration failed",
    )
    _require(bool(artifact["stopped_reason"]), "stopped reason missing")
    _require(
        artifact["expected_alembic_head"] == ALEMBIC_HEAD,
        "expected Alembic head mismatch",
    )
    _require(
        artifact["verified_alembic_head"] == ALEMBIC_HEAD,
        "verified Alembic head mismatch",
    )
    _require(
        type(artifact["github_run_id"]) is int and artifact["github_run_id"] > 0,
        "invalid run id",
    )
    _require(
        type(artifact["github_run_attempt"]) is int
        and artifact["github_run_attempt"] > 0,
        "invalid run attempt",
    )
    for field, value in artifact.items():
        if isinstance(value, str):
            _ascii(value, f"attestation {field}")
    _parse_timestamp(artifact["verified_at"], now=current)
    evidence_sha = validate_alembic_evidence(
        alembic_evidence, release_sha=approved_release_sha, now=current
    )
    _require(
        artifact["alembic_evidence_sha256"] == evidence_sha,
        "Alembic evidence binding mismatch",
    )
    payload = canonical_json({key: artifact[key] for key in ATTESTATION_PAYLOAD_FIELDS})
    _require(
        hashlib.sha256(payload).hexdigest() == artifact["artifact_sha256"],
        "attestation checksum mismatch",
    )
    config, public_key = load_trust_config(trust_config_path)
    _require(
        artifact["signature_algorithm"] == config["algorithm"],
        "signature algorithm mismatch",
    )
    _require(
        artifact["signing_key_id"] == config["approved_key_id"],
        "untrusted signing key id",
    )
    try:
        signature = base64.b64decode(artifact["artifact_signature"], validate=True)
        _require(len(signature) == 64, "invalid Ed25519 signature length")
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, payload)
    except (ValueError, binascii.Error, InvalidSignature) as exc:
        raise VerificationError("attestation signature verification failed") from exc
    return artifact


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--attestation-file", type=Path, required=True)
    parser.add_argument("--alembic-evidence-file", type=Path, required=True)
    parser.add_argument("--approved-release-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main():
    args = parse_args()
    now = datetime.now(timezone.utc)
    artifact = validate_artifact(
        load_json(args.attestation_file),
        approved_release_sha=args.approved_release_sha,
        alembic_evidence=load_json(args.alembic_evidence_file),
        now=now,
    )
    handoff = dict(artifact)
    handoff["handoff_verified_at"] = now.isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(handoff, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"MIGRATION_ATTESTATION_VERIFIED {artifact['artifact_sha256']}")


if __name__ == "__main__":
    main()
