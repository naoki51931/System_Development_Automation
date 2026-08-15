from datetime import datetime, timezone

import pytest

from scripts.verify_production_migration_attestation import (
    ALEMBIC_HEAD,
    VerificationError,
    load_artifact,
    validate_artifact,
    verify,
)


DIGEST = "a" * 64
IMAGE = f"557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod@sha256:{DIGEST}"
TASK_DEFINITION = (
    "arn:aws:ecs:eu-west-2:557604519341:task-definition/ai-platform-prod-migration:7"
)
TASK_ARN = (
    "arn:aws:ecs:eu-west-2:557604519341:task/"
    "ai-platform-prod/1234567890abcdef1234567890abcdef"
)


class ECS:
    def __init__(
        self,
        *,
        status="STOPPED",
        exit_code=0,
        digest=f"sha256:{DIGEST}",
        task_definition=TASK_DEFINITION,
        stopped_reason="Essential container in task exited",
    ):
        self.status = status
        self.exit_code = exit_code
        self.digest = digest
        self.task_definition = task_definition
        self.stopped_reason = stopped_reason

    def describe_tasks(self, **kwargs):
        assert kwargs == {"cluster": "ai-platform-prod", "tasks": [TASK_ARN]}
        return {
            "failures": [],
            "tasks": [
                {
                    "lastStatus": self.status,
                    "clusterArn": "arn:aws:ecs:eu-west-2:557604519341:cluster/ai-platform-prod",
                    "taskArn": TASK_ARN,
                    "taskDefinitionArn": self.task_definition,
                    "stoppedReason": self.stopped_reason,
                    "containers": [
                        {
                            "name": "migration",
                            "essential": True,
                            "exitCode": self.exit_code,
                            "imageDigest": self.digest,
                        }
                    ],
                }
            ],
        }

    def describe_task_definition(self, **kwargs):
        assert kwargs == {"taskDefinition": TASK_DEFINITION}
        return {
            "taskDefinition": {
                "containerDefinitions": [
                    {
                        "name": "migration",
                        "image": IMAGE,
                        "command": ["alembic", "upgrade", "head"],
                    }
                ]
            }
        }


def call(client):
    return verify(
        client,
        release_sha="b" * 40,
        approved_release_sha="b" * 40,
        cluster="ai-platform-prod",
        task_arn=TASK_ARN,
        task_definition_arn=TASK_DEFINITION,
        expected_image_uri=IMAGE,
        verified_alembic_head=ALEMBIC_HEAD,
        alembic_verification_method="approved migration verification task",
        alembic_verification_reference="run-123",
        github_run_id=123,
        github_run_attempt=1,
        github_sha="b" * 40,
        github_ref="refs/heads/master",
        verified_at="2026-08-15T00:00:00Z",
        signature="signed-payload",
        signing_key_id="prod-release-1",
        signature_verifier=lambda payload, signature, key_id: signature
        == "signed-payload",
        now=datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc),
    )


def test_verified_attestation_contains_required_non_secret_evidence():
    artifact = call(ECS())
    assert artifact["resolved_image_digest"] == f"sha256:{DIGEST}"
    assert artifact["exit_code"] == 0
    assert artifact["expected_alembic_head"] == ALEMBIC_HEAD
    assert artifact["verified_alembic_head"] == ALEMBIC_HEAD
    assert len(artifact["artifact_sha256"]) == 64
    assert not any("secret" in key.lower() for key in artifact)


@pytest.mark.parametrize(
    "client",
    [
        ECS(status="RUNNING"),
        ECS(exit_code=1),
        ECS(digest="sha256:" + "c" * 64),
        ECS(task_definition=TASK_DEFINITION.replace(":7", ":8")),
        ECS(stopped_reason=""),
    ],
)
def test_attestation_fails_closed_for_untrusted_task_results(client):
    with pytest.raises(VerificationError):
        call(client)


def test_attestation_rejects_wrong_account_region_repository_and_digest():
    for image in (
        IMAGE.replace("557604519341", "000000000000"),
        IMAGE.replace("eu-west-2", "us-east-1"),
        IMAGE.replace("ai-platform-prod@", "wrong@"),
        IMAGE.replace(DIGEST, "ABC"),
    ):
        with pytest.raises(VerificationError):
            verify(
                ECS(),
                release_sha="b" * 40,
                approved_release_sha="b" * 40,
                cluster="ai-platform-prod",
                task_arn=TASK_ARN,
                task_definition_arn=TASK_DEFINITION,
                expected_image_uri=image,
                verified_alembic_head=ALEMBIC_HEAD,
                alembic_verification_method="approved migration verification task",
                alembic_verification_reference="run-123",
                github_run_id=123,
                github_run_attempt=1,
                github_sha="b" * 40,
                github_ref="refs/heads/master",
                verified_at="2026-08-15T00:00:00Z",
                signature="signed-payload",
                signing_key_id="prod-release-1",
                signature_verifier=lambda payload, signature, key_id: True,
                now=datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc),
            )


@pytest.mark.parametrize(
    ("cluster", "task_arn"),
    [
        ("wrong-cluster", TASK_ARN),
        ("ai-platform-prod", TASK_ARN.replace("eu-west-2", "us-east-1")),
        ("ai-platform-prod", TASK_ARN.replace("557604519341", "000000000000")),
        ("ai-platform-prod", TASK_ARN.replace("ai-platform-prod/", "wrong/")),
    ],
)
def test_attestation_rejects_task_outside_production_boundary(cluster, task_arn):
    with pytest.raises(VerificationError):
        verify(
            ECS(),
            release_sha="b" * 40,
            approved_release_sha="b" * 40,
            cluster=cluster,
            task_arn=task_arn,
            task_definition_arn=TASK_DEFINITION,
            expected_image_uri=IMAGE,
            verified_alembic_head=ALEMBIC_HEAD,
            alembic_verification_method="approved migration verification task",
            alembic_verification_reference="run-123",
            github_run_id=123,
            github_run_attempt=1,
            github_sha="b" * 40,
            github_ref="refs/heads/master",
            verified_at="2026-08-15T00:00:00Z",
            signature="signed-payload",
            signing_key_id="prod-release-1",
            signature_verifier=lambda payload, signature, key_id: True,
            now=datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc),
        )


def test_stored_artifact_checksum_and_signature_fail_closed_on_tamper():
    artifact = call(ECS())
    validate_artifact(
        artifact,
        approved_release_sha="b" * 40,
        signature_verifier=lambda payload, signature, key_id: True,
        now=datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc),
    )
    for field, value in (
        ("release_sha", "c" * 40),
        ("migration_task_arn", TASK_ARN.replace("1234", "abcd")),
        ("app_image_uri", IMAGE.replace(DIGEST, "b" * 64)),
        ("verified_alembic_head", "000000000000"),
        ("verified_at", "2026-08-15T00:01:00Z"),
    ):
        tampered = dict(artifact)
        tampered[field] = value
        with pytest.raises(VerificationError, match="checksum"):
            validate_artifact(
                tampered,
                approved_release_sha="b" * 40,
                signature_verifier=lambda payload, signature, key_id: True,
                now=datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc),
            )


@pytest.mark.parametrize(
    "timestamp",
    ["2026-08-14T00:00:00Z", "2026-08-15T01:06:00Z", "not-a-timestamp"],
)
def test_timestamp_freshness_is_fail_closed(timestamp):
    with pytest.raises(VerificationError):
        verify(
            ECS(),
            release_sha="b" * 40,
            approved_release_sha="b" * 40,
            cluster="ai-platform-prod",
            task_arn=TASK_ARN,
            task_definition_arn=TASK_DEFINITION,
            expected_image_uri=IMAGE,
            verified_alembic_head=ALEMBIC_HEAD,
            alembic_verification_method="approved migration verification task",
            alembic_verification_reference="run-123",
            github_run_id=123,
            github_run_attempt=1,
            github_sha="b" * 40,
            github_ref="refs/heads/master",
            verified_at=timestamp,
            signature="signed-payload",
            signing_key_id="prod-release-1",
            signature_verifier=lambda payload, signature, key_id: True,
            now=datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"signature": None},
        {"signature": "signed-payload", "signature_verifier": lambda *_: False},
        {"approved_release_sha": "c" * 40},
        {"alembic_verification_method": "operator typed value"},
    ],
)
def test_signature_release_and_provenance_contracts_fail_closed(kwargs):
    base = {
        "release_sha": "b" * 40,
        "approved_release_sha": "b" * 40,
        "cluster": "ai-platform-prod",
        "task_arn": TASK_ARN,
        "task_definition_arn": TASK_DEFINITION,
        "expected_image_uri": IMAGE,
        "verified_alembic_head": ALEMBIC_HEAD,
        "alembic_verification_method": "approved migration verification task",
        "alembic_verification_reference": "run-123",
        "github_run_id": 123,
        "github_run_attempt": 1,
        "github_sha": "b" * 40,
        "github_ref": "refs/heads/master",
        "verified_at": "2026-08-15T00:00:00Z",
        "signature": "signed-payload",
        "signing_key_id": "prod-release-1",
        "signature_verifier": lambda payload, signature, key_id: True,
        "now": datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc),
    }
    base.update(kwargs)
    with pytest.raises(VerificationError):
        verify(ECS(), **base)


def test_artifact_loader_rejects_duplicate_json_keys(tmp_path):
    path = tmp_path / "attestation.json"
    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(VerificationError, match="duplicate"):
        load_artifact(path)
