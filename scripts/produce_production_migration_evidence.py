"""Create signed Production evidence only from AWS/GitHub machine results.

This program is intended for the protected producer workflow. It accepts no
human-provided observed Alembic head, task identity, method, or reference.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from scripts.verify_production_migration_attestation import (
    ACCOUNT,
    ALEMBIC_HEAD,
    ATTESTATION_PAYLOAD_FIELDS,
    IMAGE,
    REGION,
    TASK,
    TASK_DEFINITION,
    WORKFLOW_JOB,
    WORKFLOW_NAME,
    WORKFLOW_REF,
    WORKFLOW_REPOSITORY,
    canonical_json,
    load_json,
    load_trust_config,
)

CLUSTER_ARN = f"arn:aws:ecs:{REGION}:{ACCOUNT}:cluster/ai-platform-prod"
VERIFICATION_DEFINITION = re.compile(
    rf"arn:aws:ecs:{REGION}:{ACCOUNT}:task-definition/"
    r"ai-platform-prod-alembic-verification:[1-9][0-9]*\Z"
)
RESULT_PATTERN = re.compile(
    r'ALEMBIC_VERIFICATION_RESULT=(\{"observed_alembic_head":"[0-9a-f]+",'
    r'"output_sha256":"[0-9a-f]{64}"\})\Z'
)


class ProducerError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ProducerError(message)


def _single_task(response, *, task_arn, definition_pattern, container_name):
    require(response.get("failures") == [], "ECS task lookup failed")
    tasks = response.get("tasks", [])
    require(len(tasks) == 1, "expected one ECS task")
    task = tasks[0]
    require(task.get("taskArn") == task_arn, "task ARN mismatch")
    require(task.get("clusterArn") == CLUSTER_ARN, "task cluster mismatch")
    require(task.get("lastStatus") == "STOPPED", "task is not stopped")
    require(
        definition_pattern.fullmatch(task.get("taskDefinitionArn", "")),
        "task definition mismatch",
    )
    containers = [
        item
        for item in task.get("containers", [])
        if item.get("name") == container_name
    ]
    require(len(containers) == 1, "expected one evidence container")
    require(containers[0].get("exitCode") == 0, "evidence task failed")
    return task, containers[0]


def produce(
    *,
    migration_response,
    verification_response,
    verification_output,
    release_sha,
    app_image_uri,
    run_id,
    run_attempt,
    verified_at,
    private_key_b64,
    trust_config_path=None,
):
    require(re.fullmatch(r"[0-9a-f]{40}", release_sha), "invalid release SHA")
    require(IMAGE.fullmatch(app_image_uri), "invalid app image")
    migration_arn = migration_response.get("tasks", [{}])[0].get("taskArn", "")
    require(TASK.fullmatch(migration_arn), "invalid migration task ARN")
    migration, migration_container = _single_task(
        migration_response,
        task_arn=migration_arn,
        definition_pattern=TASK_DEFINITION,
        container_name="migration",
    )
    verification_arn = verification_response.get("tasks", [{}])[0].get("taskArn", "")
    require(TASK.fullmatch(verification_arn), "invalid verification task ARN")
    verification, verification_container = _single_task(
        verification_response,
        task_arn=verification_arn,
        definition_pattern=VERIFICATION_DEFINITION,
        container_name="alembic-verification",
    )
    match = RESULT_PATTERN.fullmatch(verification_output.strip())
    require(match is not None, "invalid verification task output")
    result = json.loads(match.group(1))
    require(result["observed_alembic_head"] == ALEMBIC_HEAD, "Alembic head mismatch")
    require(
        migration_container.get("imageDigest") == app_image_uri.split("@", 1)[1],
        "migration digest mismatch",
    )
    require(
        verification_container.get("imageDigest") == app_image_uri.split("@", 1)[1],
        "verification digest mismatch",
    )
    evidence = {
        "schema_version": 1,
        "release_sha": release_sha,
        "aws_account_id": ACCOUNT,
        "aws_region": REGION,
        "ecs_cluster_arn": CLUSTER_ARN,
        "app_image_uri": app_image_uri,
        "verification_task_arn": verification_arn,
        "verification_task_definition_arn": verification["taskDefinitionArn"],
        "verification_task_definition_revision": int(
            verification["taskDefinitionArn"].rsplit(":", 1)[1]
        ),
        "exit_code": 0,
        "expected_alembic_head": ALEMBIC_HEAD,
        "observed_alembic_head": result["observed_alembic_head"],
        "verified_at": verified_at,
        "output_sha256": result["output_sha256"],
        "github_repository": WORKFLOW_REPOSITORY,
        "github_workflow": WORKFLOW_NAME,
        "github_job": WORKFLOW_JOB,
        "github_ref": WORKFLOW_REF,
        "github_run_id": run_id,
        "github_run_attempt": run_attempt,
    }
    definition_revision = int(migration["taskDefinitionArn"].rsplit(":", 1)[1])
    artifact = {
        "schema_version": 2,
        "release_sha": release_sha,
        "aws_account_id": ACCOUNT,
        "aws_region": REGION,
        "ecs_cluster_arn": CLUSTER_ARN,
        "migration_task_arn": migration_arn,
        "migration_task_definition_arn": migration["taskDefinitionArn"],
        "migration_task_definition_revision": definition_revision,
        "app_image_uri": app_image_uri,
        "resolved_image_digest": migration_container["imageDigest"],
        "container_name": "migration",
        "exit_code": 0,
        "stopped_reason": migration.get("stoppedReason", ""),
        "expected_alembic_head": ALEMBIC_HEAD,
        "verified_alembic_head": result["observed_alembic_head"],
        "verified_at": verified_at,
        "github_repository": WORKFLOW_REPOSITORY,
        "github_workflow": WORKFLOW_NAME,
        "github_run_id": run_id,
        "github_run_attempt": run_attempt,
        "github_job": WORKFLOW_JOB,
        "github_sha": release_sha,
        "github_ref": WORKFLOW_REF,
        "signature_algorithm": "Ed25519",
        "signing_key_id": "production-release-2026-01",
        "alembic_evidence_sha256": hashlib.sha256(canonical_json(evidence)).hexdigest(),
    }
    payload = canonical_json({key: artifact[key] for key in ATTESTATION_PAYLOAD_FIELDS})
    artifact["artifact_sha256"] = hashlib.sha256(payload).hexdigest()
    try:
        private_key = Ed25519PrivateKey.from_private_bytes(
            base64.b64decode(private_key_b64, validate=True)
        )
    except (ValueError, TypeError) as exc:
        raise ProducerError("invalid protected Production signer") from exc
    trust_args = () if trust_config_path is None else (trust_config_path,)
    trust, trusted_public_key = load_trust_config(*trust_args)
    derived_public_key = private_key.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    require(
        derived_public_key == trusted_public_key,
        "signer does not match reviewed trust root",
    )
    require(
        trust["approved_key_id"] == artifact["signing_key_id"],
        "signing key id mismatch",
    )
    artifact["artifact_signature"] = base64.b64encode(
        private_key.sign(payload)
    ).decode()
    return evidence, artifact


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--migration-task-json", type=Path, required=True)
    parser.add_argument("--verification-task-json", type=Path, required=True)
    parser.add_argument("--verification-output", type=Path, required=True)
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--app-image-uri", required=True)
    parser.add_argument("--github-run-id", type=int, required=True)
    parser.add_argument("--github-run-attempt", type=int, required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--attestation-output", type=Path, required=True)
    return parser.parse_args()


def write_secure_json(path, value):
    require(not path.is_symlink(), "evidence output must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(not path.parent.is_symlink(), "evidence directory must not be a symlink")
    descriptor, temporary = tempfile.mkstemp(
        prefix=".production-evidence-", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    args = parse_args()
    private_key_b64 = os.environ.get("PRODUCTION_ATTESTATION_SIGNING_KEY_B64", "")
    require(private_key_b64, "protected Production signer is required")
    verified_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    evidence, artifact = produce(
        migration_response=load_json(args.migration_task_json),
        verification_response=load_json(args.verification_task_json),
        verification_output=args.verification_output.read_text(encoding="utf-8"),
        release_sha=args.release_sha,
        app_image_uri=args.app_image_uri,
        run_id=args.github_run_id,
        run_attempt=args.github_run_attempt,
        verified_at=verified_at,
        private_key_b64=private_key_b64,
    )
    for path, value in (
        (args.evidence_output, evidence),
        (args.attestation_output, artifact),
    ):
        write_secure_json(path, value)


if __name__ == "__main__":
    main()
