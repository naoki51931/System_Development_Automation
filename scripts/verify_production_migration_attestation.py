"""Read-only verifier for a Production ECS migration task attestation."""

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ACCOUNT = "557604519341"
REGION = "eu-west-2"
REPOSITORY = "ai-platform-prod"
ALEMBIC_HEAD = "8d4f2a7c9b11"
IMAGE_PATTERN = re.compile(
    rf"^{ACCOUNT}\.dkr\.ecr\.{REGION}\.amazonaws\.com/"
    rf"{REPOSITORY}@sha256:([0-9a-f]{{64}})$"
)
TASK_DEFINITION_PATTERN = re.compile(
    rf"^arn:aws:ecs:{REGION}:{ACCOUNT}:task-definition/"
    rf"ai-platform-prod-migration:[1-9][0-9]*$"
)
CLUSTER = f"arn:aws:ecs:{REGION}:{ACCOUNT}:cluster/ai-platform-prod"
TASK_PATTERN = re.compile(
    rf"^arn:aws:ecs:{REGION}:{ACCOUNT}:task/ai-platform-prod/[0-9a-f]{{32}}$"
)


class VerificationError(RuntimeError):
    pass


def _require(condition, message):
    if not condition:
        raise VerificationError(message)


def verify(
    ecs,
    *,
    release_sha,
    cluster,
    task_arn,
    task_definition_arn,
    expected_image_uri,
    verified_alembic_head,
    verified_at=None,
):
    image_match = IMAGE_PATTERN.fullmatch(expected_image_uri)
    _require(image_match is not None, "approved image is not the Production digest URI")
    _require(
        re.fullmatch(r"[0-9a-f]{40}", release_sha) is not None, "invalid release SHA"
    )
    _require(cluster in ("ai-platform-prod", CLUSTER), "unexpected Production cluster")
    _require(
        TASK_PATTERN.fullmatch(task_arn) is not None, "unexpected migration task ARN"
    )
    _require(
        TASK_DEFINITION_PATTERN.fullmatch(task_definition_arn) is not None,
        "unexpected migration task definition ARN",
    )
    _require(verified_alembic_head == ALEMBIC_HEAD, "Alembic head was not verified")

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
    definitions = definition.get("containerDefinitions", [])
    migration_definitions = [
        item for item in definitions if item.get("name") == "migration"
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
        "release_sha": release_sha,
        "ecs_cluster": task["clusterArn"],
        "migration_task_arn": task["taskArn"],
        "migration_task_definition": task_definition_arn,
        "expected_app_image_uri": expected_image_uri,
        "resolved_image_digest": resolved_digest,
        "task_stopped_reason": task.get("stoppedReason", ""),
        "essential_container_exit_code": container["exitCode"],
        "expected_alembic_head": ALEMBIC_HEAD,
        "verified_alembic_head": verified_alembic_head,
        "verified_at": verified_at or datetime.now(timezone.utc).isoformat(),
    }
    canonical = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode()
    artifact["artifact_sha256"] = hashlib.sha256(canonical).hexdigest()
    return artifact


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--cluster", required=True)
    parser.add_argument("--task-arn", required=True)
    parser.add_argument("--task-definition-arn", required=True)
    parser.add_argument("--expected-image-uri", required=True)
    parser.add_argument("--verified-alembic-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    import boto3

    ecs = boto3.client("ecs", region_name=REGION)
    artifact = verify(
        ecs,
        release_sha=args.release_sha,
        cluster=args.cluster,
        task_arn=args.task_arn,
        task_definition_arn=args.task_definition_arn,
        expected_image_uri=args.expected_image_uri,
        verified_alembic_head=args.verified_alembic_head,
    )
    args.output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(f"MIGRATION_ATTESTATION_VERIFIED {artifact['artifact_sha256']}")


if __name__ == "__main__":
    main()
