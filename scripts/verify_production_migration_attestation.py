"""Read-only verifier for a signed Production ECS migration attestation.

The verifier is the trust boundary for the release workflow. Terraform consumes
the resulting canonical artifact but does not perform cryptographic operations.
"""

import argparse
import base64
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ACCOUNT = "557604519341"
REGION = "eu-west-2"
REPOSITORY = "ai-platform-prod"
ALEMBIC_HEAD = "8d4f2a7c9b11"
SCHEMA_VERSION = 1
MAX_ATTESTATION_AGE = timedelta(hours=24)
MAX_CLOCK_SKEW = timedelta(minutes=5)
WORKFLOW_REPOSITORY = "naoki51931/System_Development_Automation"
WORKFLOW_NAME = "production-release"
WORKFLOW_JOB = "migration-attestation"
IMAGE_PATTERN = re.compile(
    rf"^{ACCOUNT}\.dkr\.ecr\.{REGION}\.amazonaws\.com/"
    rf"{REPOSITORY}@sha256:([0-9a-f]{{64}})$"
)
TASK_DEFINITION_PATTERN = re.compile(
    rf"^arn:aws:ecs:{REGION}:{ACCOUNT}:task-definition/"
    rf"ai-platform-prod-migration:([1-9][0-9]*)$"
)
CLUSTER = f"arn:aws:ecs:{REGION}:{ACCOUNT}:cluster/ai-platform-prod"
TASK_PATTERN = re.compile(
    rf"^arn:aws:ecs:{REGION}:{ACCOUNT}:task/ai-platform-prod/[0-9a-f]{{32}}$"
)
SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
HEX64_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class VerificationError(RuntimeError):
    pass


def _require(condition, message):
    if not condition:
        raise VerificationError(message)


def _parse_timestamp(value, *, now=None):
    _require(
        isinstance(value, str) and value.endswith("Z"), "timestamp must be UTC RFC3339"
    )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise VerificationError("invalid verification timestamp") from exc
    _require(parsed.tzinfo is not None, "timestamp timezone is required")
    parsed = parsed.astimezone(timezone.utc)
    current = now or datetime.now(timezone.utc)
    _require(
        parsed <= current + MAX_CLOCK_SKEW, "verification timestamp is in the future"
    )
    _require(current - parsed <= MAX_ATTESTATION_AGE, "migration attestation is stale")
    return parsed


def _canonical_payload(artifact):
    unsigned = {
        key: value
        for key, value in artifact.items()
        if key not in {"artifact_sha256", "artifact_signature"}
    }
    return json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _verify_signature(
    payload,
    *,
    signature,
    signature_algorithm,
    signing_key_id,
    trusted_public_keys,
    signature_verifier=None,
):
    _require(signature_algorithm == "Ed25519", "unsupported signature algorithm")
    _require(bool(signing_key_id), "signing key id is required")
    _require(
        isinstance(signature, str) and signature, "unsigned attestation is forbidden"
    )
    if signature_verifier is not None:
        _require(
            signature_verifier(payload, signature, signing_key_id),
            "attestation signature verification failed",
        )
        return
    key = (trusted_public_keys or {}).get(signing_key_id)
    _require(key is not None, "untrusted attestation signing key")
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(
            base64.b64decode(signature, validate=True), payload
        )
    except (ValueError, TypeError) as exc:
        raise VerificationError("attestation signature verification failed") from exc


def validate_artifact(
    artifact,
    *,
    approved_release_sha,
    trusted_public_keys=None,
    signature_verifier=None,
    now=None,
):
    """Validate a stored artifact before it is handed to Terraform."""
    _require(isinstance(artifact, dict), "attestation must be a JSON object")
    _require(
        artifact.get("schema_version") == SCHEMA_VERSION,
        "unsupported attestation schema",
    )
    checksum = artifact.get("artifact_sha256", "")
    _require(HEX64_PATTERN.fullmatch(checksum) is not None, "invalid artifact checksum")
    computed = hashlib.sha256(_canonical_payload(artifact)).hexdigest()
    _require(computed == checksum, "attestation checksum mismatch")
    _require(
        artifact.get("release_sha") == approved_release_sha,
        "artifact release SHA mismatch",
    )
    _require(
        SHA_PATTERN.fullmatch(artifact.get("github_sha", "")) is not None,
        "invalid artifact workflow SHA",
    )
    _parse_timestamp(artifact.get("verified_at"), now=now)
    _verify_signature(
        _canonical_payload(artifact),
        signature=artifact.get("artifact_signature"),
        signature_algorithm=artifact.get("signature_algorithm"),
        signing_key_id=artifact.get("signing_key_id"),
        trusted_public_keys=trusted_public_keys,
        signature_verifier=signature_verifier,
    )
    return artifact


def load_artifact(path):
    """Load a handoff artifact while rejecting duplicate JSON keys."""

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise VerificationError(f"duplicate attestation field: {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError("invalid attestation JSON") from exc


def verify(
    ecs,
    *,
    release_sha,
    approved_release_sha,
    cluster,
    task_arn,
    task_definition_arn,
    expected_image_uri,
    verified_alembic_head,
    alembic_verification_method,
    alembic_verification_reference,
    github_repository=WORKFLOW_REPOSITORY,
    github_workflow=WORKFLOW_NAME,
    github_run_id,
    github_run_attempt,
    github_job=WORKFLOW_JOB,
    github_sha=None,
    github_ref=None,
    verified_at=None,
    signature=None,
    signature_algorithm="Ed25519",
    signing_key_id=None,
    trusted_public_keys=None,
    signature_verifier=None,
    now=None,
):
    image_match = IMAGE_PATTERN.fullmatch(expected_image_uri)
    _require(image_match is not None, "approved image is not the Production digest URI")
    _require(
        SHA_PATTERN.fullmatch(release_sha or "") is not None, "invalid release SHA"
    )
    _require(
        release_sha == approved_release_sha, "release SHA is not the approved release"
    )
    _require(github_sha == release_sha, "workflow SHA is not the approved release")
    _require(github_repository == WORKFLOW_REPOSITORY, "unexpected workflow repository")
    _require(github_workflow == WORKFLOW_NAME, "unexpected workflow name")
    _require(github_job == WORKFLOW_JOB, "unexpected workflow job")
    _require(
        isinstance(github_run_id, int) and github_run_id > 0, "invalid workflow run id"
    )
    _require(
        isinstance(github_run_attempt, int) and github_run_attempt > 0,
        "invalid workflow run attempt",
    )
    _require(
        github_ref == "refs/heads/master",
        "invalid workflow ref",
    )
    _require(cluster in ("ai-platform-prod", CLUSTER), "unexpected Production cluster")
    _require(
        TASK_PATTERN.fullmatch(task_arn or "") is not None,
        "unexpected migration task ARN",
    )
    definition_match = TASK_DEFINITION_PATTERN.fullmatch(task_definition_arn or "")
    _require(definition_match is not None, "unexpected migration task definition ARN")
    _require(verified_alembic_head == ALEMBIC_HEAD, "Alembic head was not verified")
    _require(
        alembic_verification_method
        in {
            "approved migration verification task",
            "read-only DB verification job",
            "migration container verification step",
        },
        "disallowed Alembic verification method",
    )
    _require(
        isinstance(alembic_verification_reference, str)
        and bool(alembic_verification_reference),
        "Alembic verification reference is required",
    )
    verified_timestamp = _parse_timestamp(verified_at, now=now)

    task_response = ecs.describe_tasks(cluster=cluster, tasks=[task_arn])
    _require(not task_response.get("failures"), "ECS task lookup failed")
    tasks = task_response.get("tasks", [])
    _require(len(tasks) == 1, "expected exactly one ECS task")
    task = tasks[0]
    _require(task.get("lastStatus") == "STOPPED", "migration task is not STOPPED")
    _require(bool(task.get("stoppedReason")), "migration task stopped reason missing")
    _require(task.get("clusterArn") == CLUSTER, "migration task cluster mismatch")
    _require(task.get("taskArn") == task_arn, "migration task ARN mismatch")
    _require(
        task.get("taskDefinitionArn") == task_definition_arn,
        "migration task definition revision mismatch",
    )

    definition = ecs.describe_task_definition(taskDefinition=task_definition_arn)[
        "taskDefinition"
    ]
    migration_definitions = [
        item
        for item in definition.get("containerDefinitions", [])
        if item.get("name") == "migration"
    ]
    _require(len(migration_definitions) == 1, "migration container definition missing")
    migration_definition = migration_definitions[0]
    _require(
        migration_definition.get("image") == expected_image_uri, "task image mismatch"
    )
    _require(
        migration_definition.get("command") == ["alembic", "upgrade", "head"],
        "migration command mismatch",
    )

    containers = [
        item for item in task.get("containers", []) if item.get("name") == "migration"
    ]
    _require(len(containers) == 1, "migration container result missing")
    container = containers[0]
    _require(
        container.get("essential") is not False, "migration container is not essential"
    )
    _require(container.get("exitCode") == 0, "migration container did not exit zero")
    resolved_digest = container.get("imageDigest", "")
    _require(
        resolved_digest == f"sha256:{image_match.group(1)}", "resolved digest mismatch"
    )

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "release_sha": release_sha,
        "aws_account_id": ACCOUNT,
        "aws_region": REGION,
        "ecs_cluster_arn": task["clusterArn"],
        "migration_task_arn": task["taskArn"],
        "migration_task_definition_arn": task_definition_arn,
        "migration_task_definition_revision": int(definition_match.group(1)),
        "app_image_uri": expected_image_uri,
        "resolved_image_digest": resolved_digest,
        "container_name": "migration",
        "exit_code": container["exitCode"],
        "stopped_reason": task["stoppedReason"],
        "expected_alembic_head": ALEMBIC_HEAD,
        "verified_alembic_head": verified_alembic_head,
        "alembic_verification_method": alembic_verification_method,
        "alembic_verification_reference": alembic_verification_reference,
        "verified_at": verified_timestamp.isoformat().replace("+00:00", "Z"),
        "github_repository": github_repository,
        "github_workflow": github_workflow,
        "github_run_id": github_run_id,
        "github_run_attempt": github_run_attempt,
        "github_job": github_job,
        "github_sha": github_sha,
        "github_ref": github_ref,
        "signature_algorithm": signature_algorithm,
        "signing_key_id": signing_key_id,
    }
    payload = _canonical_payload(artifact)
    artifact["artifact_sha256"] = hashlib.sha256(payload).hexdigest()
    artifact["artifact_signature"] = signature
    _require(
        HEX64_PATTERN.fullmatch(artifact["artifact_sha256"]) is not None,
        "invalid artifact checksum",
    )
    _verify_signature(
        payload,
        signature=signature,
        signature_algorithm=signature_algorithm,
        signing_key_id=signing_key_id,
        trusted_public_keys=trusted_public_keys,
        signature_verifier=signature_verifier,
    )
    return artifact


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--approved-release-sha", required=True)
    parser.add_argument("--cluster", required=True)
    parser.add_argument("--task-arn", required=True)
    parser.add_argument("--task-definition-arn", required=True)
    parser.add_argument("--expected-image-uri", required=True)
    parser.add_argument("--verified-alembic-head", required=True)
    parser.add_argument("--alembic-verification-method", required=True)
    parser.add_argument("--alembic-verification-reference", required=True)
    parser.add_argument("--github-run-id", type=int, required=True)
    parser.add_argument("--github-run-attempt", type=int, required=True)
    parser.add_argument("--github-sha", required=True)
    parser.add_argument("--github-ref", required=True)
    parser.add_argument("--verified-at", required=True)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--signature-algorithm", default="Ed25519")
    parser.add_argument("--signing-key-id", required=True)
    parser.add_argument("--public-key-b64", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    import boto3

    ecs = boto3.client("ecs", region_name=REGION)
    public_key = base64.b64decode(args.public_key_b64, validate=True)
    artifact = verify(
        ecs,
        release_sha=args.release_sha,
        approved_release_sha=args.approved_release_sha,
        cluster=args.cluster,
        task_arn=args.task_arn,
        task_definition_arn=args.task_definition_arn,
        expected_image_uri=args.expected_image_uri,
        verified_alembic_head=args.verified_alembic_head,
        alembic_verification_method=args.alembic_verification_method,
        alembic_verification_reference=args.alembic_verification_reference,
        github_run_id=args.github_run_id,
        github_run_attempt=args.github_run_attempt,
        github_sha=args.github_sha,
        github_ref=args.github_ref,
        verified_at=args.verified_at,
        signature=args.signature,
        signature_algorithm=args.signature_algorithm,
        signing_key_id=args.signing_key_id,
        trusted_public_keys={args.signing_key_id: public_key},
    )
    args.output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(f"MIGRATION_ATTESTATION_VERIFIED {artifact['artifact_sha256']}")


if __name__ == "__main__":
    main()
