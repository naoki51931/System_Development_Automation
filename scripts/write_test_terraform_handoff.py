"""Write non-cryptographic TEST ONLY Terraform handoff data for mock-provider tests."""

import json
from datetime import datetime, timezone
from pathlib import Path


def main():
    now = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    digest = "a" * 64
    release = "c" * 40
    data = {
        "schema_version": 2,
        "release_sha": release,
        "aws_account_id": "557604519341",
        "aws_region": "eu-west-2",
        "ecs_cluster_arn": "arn:aws:ecs:eu-west-2:557604519341:cluster/ai-platform-prod",
        "migration_task_arn": "arn:aws:ecs:eu-west-2:557604519341:task/ai-platform-prod/1234567890abcdef1234567890abcdef",
        "migration_task_definition_arn": "arn:aws:ecs:eu-west-2:557604519341:task-definition/ai-platform-prod-migration:7",
        "migration_task_definition_revision": 7,
        "app_image_uri": f"557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod@sha256:{digest}",
        "resolved_image_digest": f"sha256:{digest}",
        "container_name": "migration",
        "exit_code": 0,
        "stopped_reason": "TEST ONLY",
        "expected_alembic_head": "8d4f2a7c9b11",
        "verified_alembic_head": "8d4f2a7c9b11",
        "verified_at": now,
        "handoff_verified_at": now,
        "github_repository": "naoki51931/System_Development_Automation",
        "github_workflow": "production-release",
        "github_run_id": 1,
        "github_run_attempt": 1,
        "github_job": "production-plan",
        "github_sha": release,
        "github_ref": "refs/heads/master",
        "signature_algorithm": "Ed25519",
        "signing_key_id": "production-release-2026-01",
        "alembic_evidence_sha256": "d" * 64,
        "artifact_sha256": "e" * 64,
        "artifact_signature": "TEST-ONLY-NOT-A-REAL-SIGNATURE",
    }
    output = Path("environment/.production-release/verified-attestation.json")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
