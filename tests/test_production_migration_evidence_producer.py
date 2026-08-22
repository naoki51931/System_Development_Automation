"""Focused tests for the protected machine-evidence producer."""

import base64
from pathlib import Path

import pytest

from scripts.produce_production_migration_evidence import ProducerError, produce
from scripts.verify_production_migration_attestation import validate_artifact

TEST_ONLY_PRIVATE_SEED = bytes(range(32))
TEST_TRUST = Path(__file__).parent / "fixtures/production_attestation_test_trust.json"
RELEASE_SHA = "b" * 40
DIGEST = "a" * 64
TASK_PREFIX = "arn:aws:ecs:eu-west-2:557604519341:task/ai-platform-prod/"
CLUSTER = "arn:aws:ecs:eu-west-2:557604519341:cluster/ai-platform-prod"


def task_response(*, task_id, definition, container, image_digest=None, exit_code=0):
    container_value = {"name": container, "exitCode": exit_code}
    if image_digest is not None:
        container_value["imageDigest"] = image_digest
    return {
        "failures": [],
        "tasks": [
            {
                "taskArn": TASK_PREFIX + task_id,
                "clusterArn": CLUSTER,
                "lastStatus": "STOPPED",
                "taskDefinitionArn": definition,
                "stoppedReason": "Essential container exited",
                "containers": [container_value],
            }
        ],
    }


def produce_valid(**updates):
    arguments = {
        "migration_response": task_response(
            task_id="1" * 32,
            definition="arn:aws:ecs:eu-west-2:557604519341:task-definition/ai-platform-prod-migration:7",
            container="migration",
            image_digest=f"sha256:{DIGEST}",
        ),
        "verification_response": task_response(
            task_id="2" * 32,
            definition="arn:aws:ecs:eu-west-2:557604519341:task-definition/ai-platform-prod-alembic-verification:11",
            container="alembic-verification",
            image_digest=f"sha256:{DIGEST}",
        ),
        "verification_output": (
            'ALEMBIC_VERIFICATION_RESULT={"observed_alembic_head":"8d4f2a7c9b11",'
            f'"output_sha256":"{"c" * 64}"}}'
        ),
        "release_sha": RELEASE_SHA,
        "app_image_uri": f"557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod@sha256:{DIGEST}",
        "run_id": 123,
        "run_attempt": 1,
        "verified_at": "2026-08-15T00:00:00Z",
        "private_key_b64": base64.b64encode(TEST_ONLY_PRIVATE_SEED).decode(),
        "trust_config_path": TEST_TRUST,
    }
    arguments.update(updates)
    return produce(**arguments)


def test_machine_results_produce_self_verifiable_bound_evidence():
    evidence, artifact = produce_valid()
    assert evidence["verification_task_definition_revision"] == 11
    assert validate_artifact(
        artifact,
        approved_release_sha=RELEASE_SHA,
        alembic_evidence=evidence,
        trust_config_path=TEST_TRUST,
        expected_producer_run_id=123,
        expected_producer_run_attempt=1,
        now=__import__("datetime").datetime(
            2026, 8, 15, 1, tzinfo=__import__("datetime").timezone.utc
        ),
    )


def test_human_style_or_failed_machine_output_is_rejected():
    with pytest.raises(ProducerError):
        produce_valid(verification_output='{"observed_alembic_head":"8d4f2a7c9b11"}')
    failed = task_response(
        task_id="2" * 32,
        definition="arn:aws:ecs:eu-west-2:557604519341:task-definition/ai-platform-prod-alembic-verification:11",
        container="alembic-verification",
        image_digest=f"sha256:{DIGEST}",
        exit_code=1,
    )
    with pytest.raises(ProducerError):
        produce_valid(verification_response=failed)


def test_repository_test_key_cannot_sign_for_production_trust_root():
    with pytest.raises(ProducerError, match="trust root"):
        produce_valid(trust_config_path=None)
