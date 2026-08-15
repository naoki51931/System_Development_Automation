from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "environment"
ECS = ROOT / "modules/ecs/main.tf"
MONITORING = ROOT / "modules/production_monitoring/main.tf"
CONSUMER_WORKFLOW = ROOT / ".github/workflows/production-release.yml"
PRODUCER_WORKFLOW = ROOT / ".github/workflows/production-migration-evidence.yml"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


ACCOUNT = "557604519341"
REGION = "eu-west-2"
APP_REPOSITORY = "ai-platform-prod"
FRONTEND_REPOSITORY = "ai-platform-prod-frontend"
DIGEST = "a" * 64


def accepted_digest(uri: str, repository: str) -> bool:
    return (
        re.fullmatch(
            rf"{ACCOUNT}\.dkr\.ecr\.{REGION}\.amazonaws\.com/"
            rf"{re.escape(repository)}@sha256:[0-9a-f]{{64}}",
            uri,
        )
        is not None
    )


def test_digest_validation_accepts_only_exact_repository_digest_uris():
    valid = f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{APP_REPOSITORY}@sha256:{DIGEST}"
    assert accepted_digest(valid, APP_REPOSITORY)

    invalid = [
        f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{APP_REPOSITORY}:latest",
        f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{APP_REPOSITORY}:release",
        f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{APP_REPOSITORY}@sha256:abc",
        f"000000000000.dkr.ecr.{REGION}.amazonaws.com/{APP_REPOSITORY}@sha256:{DIGEST}",
        f"{ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com/{APP_REPOSITORY}@sha256:{DIGEST}",
        f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/wrong@sha256:{DIGEST}",
        f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{APP_REPOSITORY}@sha256:{'A' * 64}",
    ]
    assert all(not accepted_digest(uri, APP_REPOSITORY) for uri in invalid)


@pytest.mark.parametrize("image_name", ["app_image_uri", "frontend_image_uri"])
def test_terraform_digest_inputs_are_fail_closed(image_name: str):
    variables = text(PRODUCTION / "variables.tf")
    block = re.search(rf'variable "{image_name}" \{{(.*?)\n\}}', variables, re.S)
    assert block
    assert "@sha256:[0-9a-f]{64}" in block.group(1)
    assert "DIGEST_INPUT_UNSUPPORTED" in block.group(1)
    assert ACCOUNT in block.group(1)
    assert REGION in block.group(1)
    assert (
        APP_REPOSITORY if image_name == "app_image_uri" else FRONTEND_REPOSITORY
    ) in block.group(1)


def test_frontend_has_dedicated_ecr_and_complete_runtime_topology():
    ecs = text(ECS)
    assert 'resource "aws_ecr_repository" "frontend"' in ecs
    assert 'name                 = "${var.name}-frontend"' in ecs
    assert 'image_tag_mutability = "IMMUTABLE"' in ecs
    assert 'encryption_type = "AES256"' in ecs
    assert 'resource "aws_ecr_lifecycle_policy" "frontend"' in ecs
    assert 'resource "aws_ecs_task_definition" "frontend"' in ecs
    assert "image = var.frontend_image" in ecs
    assert re.search(r'command\s*=\s*\[\s*"node",\s*"server.js"\s*\]', ecs)
    assert 'resource "aws_ecs_service" "frontend"' in ecs
    assert 'resource "aws_cloudwatch_log_group" "release"' in ecs
    assert 'resource "aws_lb_target_group" "frontend"' in ecs
    assert 'resource "aws_lb_listener_rule" "frontend"' in ecs
    assert 'resource "aws_lb_listener_rule" "backend_api"' in ecs
    for path in ("/api/*", "/docs*", "/openapi.json", "/health", "/static/*"):
        assert f'"{path}"' in ecs
    assert re.search(r'path\s*=\s*"/login"', ecs)


def test_backend_worker_and_migration_share_one_app_digest():
    ecs = text(ECS)
    for resource in ("release_backend", "worker", "migration"):
        block = re.search(
            rf'resource "aws_ecs_task_definition" "{resource}" \{{(.*?)(?=\nresource |\noutput |\Z)',
            ecs,
            re.S,
        )
        assert block and "image = var.app_image" in block.group(1)
    assert re.search(
        r'command\s*=\s*\[\s*"python",\s*"-m",\s*"app.workers.runner"\s*\]',
        ecs,
    )
    assert re.search(r'command\s*=\s*\[\s*"alembic",\s*"upgrade",\s*"head"\s*\]', ecs)


def test_worker_is_independent_low_traffic_service_with_monitoring():
    ecs = text(ECS)
    worker = re.search(
        r'resource "aws_ecs_task_definition" "worker" \{(.*?)(?=\nresource )',
        ecs,
        re.S,
    )
    assert worker
    assert 'cpu                      = "256"' in worker.group(1)
    assert 'memory                   = "512"' in worker.group(1)
    assert 'resource "aws_ecs_service" "worker"' in ecs
    monitoring = text(MONITORING)
    for metric in (
        "RunningTaskCount",
        "CPUUtilization",
        "MemoryUtilization",
        "WorkerHeartbeatAgeSeconds",
        "DeadLetterCount",
    ):
        assert metric in monitoring
    assert 'namespace           = "SystemNavigator/Production"' in monitoring
    assert 'statistic           = "Maximum"' in monitoring


def test_migration_is_definition_only_and_runtime_gate_matches_exact_digest():
    root = text(PRODUCTION / "variables.tf")
    main = text(PRODUCTION / "main.tf")
    ecs = text(ECS)
    assert 'check "migration_before_release_runtime"' in root
    assert 'resource "terraform_data" "release_runtime_gate"' in main
    assert "precondition" in main
    assert (
        'migration_attestation_path = "${path.module}/.production-release/verified-attestation.json"'
        in main
    )
    assert 'variable "migration_attestation"' not in root
    assert "local.migration_attestation.app_image_uri" in main
    assert "local.migration_attestation.resolved_image_digest" in main
    assert "local.migration_attestation.artifact_signature" in main
    assert "handoff_verified_at" in main
    assert not (ROOT / "scripts/write_test_terraform_handoff.py").exists()
    assert "environment/.production-release" not in text(
        ROOT / "tests/terraform/production_release_gate_fixture/main.tf"
    )
    assert "var.approved_release_sha" in main
    assert "depends_on             = [terraform_data.release_runtime_gate]" in main
    assert "MIGRATION_SEQUENCE_UNSAFE" in root
    assert 'resource "aws_ecs_task_definition" "migration"' in ecs
    assert 'resource "aws_ecs_task_definition" "alembic_verification"' in ecs
    assert 'resource "aws_ecs_service" "migration"' not in ecs
    assert not re.search(r'resource "aws_ecs_task"', ecs)
    assert "local-exec" not in ecs
    assert "count        = var.enable_release_runtime ? 1 : 0" in ecs


def test_protected_workflows_fix_control_plane_producer_and_full_plan():
    consumer = text(CONSUMER_WORKFLOW)
    producer = text(PRODUCER_WORKFLOW)
    assert "release_sha:" not in consumer
    assert "path: control-plane" in consumer
    assert "path: release-tree" in consumer
    assert "git -C control-plane merge-base --is-ancestor" in consumer
    assert (
        "control-plane/scripts/verify_production_migration_attestation.py" in consumer
    )
    assert 'gh api "repos/$GITHUB_REPOSITORY/actions/runs/$PRODUCER_RUN_ID"' in consumer
    assert "actions/runs/$PRODUCER_RUN_ID/attempts/$run_attempt/jobs" in consumer
    assert '.conclusion == "success"' in consumer
    assert "terraform plan" in consumer
    assert "-target" not in consumer
    assert "environment: production" in consumer
    assert "environment: production" in producer
    assert "--observed" not in producer
    assert "PRODUCTION_ATTESTATION_SIGNING_KEY_B64" in producer
    for workflow in (consumer, producer):
        for line in workflow.splitlines():
            if "uses:" in line:
                reference = line.split("uses:", 1)[1].split("#", 1)[0].strip()
                assert re.search(r"@[0-9a-f]{40}$", reference), reference


def test_external_providers_are_fail_closed_and_not_launch_ready():
    variables = text(PRODUCTION / "variables.tf")
    ecs = text(ECS)
    assert 'variable "external_launch_ready"' in variables
    assert "condition     = !var.external_launch_ready" in variables
    assert "PROVIDER_NOT_CONFIGURED" in variables
    for flag in ("COGNITO", "STRIPE", "SES", "MOCK_AI", "MOCK_PAYMENT", "MOCK_EMAIL"):
        assert f'{{ name = "APP_ENABLE_{flag}", value = "false" }}' in ecs
    assert 'output "external_launch_ready" { value = false }' in text(
        PRODUCTION / "outputs.tf"
    )


def test_existing_production_backend_addresses_are_preserved_additively():
    ecs = text(ECS)
    for address in (
        'resource "aws_ecr_repository" "app"',
        'resource "aws_lb" "main"',
        'resource "aws_lb_target_group" "app"',
        'resource "aws_lb_listener" "http"',
        'resource "aws_ecs_task_definition" "app"',
        'resource "aws_ecs_task_definition" "app_low_traffic"',
        'resource "aws_ecs_service" "app"',
    ):
        assert address in ecs
    assert "task_definition = var.enable_release_runtime ?" in ecs
    assert 'module "network"' in text(PRODUCTION / "main.tf")
    assert 'module "database"' in text(PRODUCTION / "main.tf")


def test_staging_idle_and_deprecated_domain_boundaries_are_untouched():
    staging = text(PRODUCTION / "staging/variables.tf")
    assert 'contains(["idle", "active"], var.staging_mode)' in staging
    assert "default     = false" in staging
    active_production = "\n".join(
        text(path) for path in [*PRODUCTION.glob("*.tf"), ECS, MONITORING]
    )
    assert "true-camera-test.com" not in active_production
