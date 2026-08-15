import pytest

from scripts.verify_production_migration_attestation import (
    ALEMBIC_HEAD,
    VerificationError,
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
        cluster="ai-platform-prod",
        task_arn=TASK_ARN,
        task_definition_arn=TASK_DEFINITION,
        expected_image_uri=IMAGE,
        verified_alembic_head=ALEMBIC_HEAD,
        verified_at="2026-08-14T00:00:00+00:00",
    )


def test_verified_attestation_contains_required_non_secret_evidence():
    artifact = call(ECS())
    assert artifact["resolved_image_digest"] == f"sha256:{DIGEST}"
    assert artifact["essential_container_exit_code"] == 0
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
                cluster="ai-platform-prod",
                task_arn=TASK_ARN,
                task_definition_arn=TASK_DEFINITION,
                expected_image_uri=image,
                verified_alembic_head=ALEMBIC_HEAD,
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
            cluster=cluster,
            task_arn=task_arn,
            task_definition_arn=TASK_DEFINITION,
            expected_image_uri=IMAGE,
            verified_alembic_head=ALEMBIC_HEAD,
        )
