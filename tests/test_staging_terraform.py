from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_BACKEND = ROOT / "environment/backend.hcl.example"
STAGING = ROOT / "environment/staging"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_backend_keys_and_prefixes_are_distinct():
    production = text(PRODUCTION_BACKEND)
    staging = text(STAGING / "backend.hcl.example")
    staging_vars = text(STAGING / "variables.tf")
    assert 'key            = "cloud-a/prod/terraform.tfstate"' in production
    assert 'key          = "system-navigator/staging/terraform.tfstate"' in staging
    assert production != staging
    assert 'default = "system-navigator-staging"' in staging_vars
    assert 'default     = "ai-platform-prod"' in text(
        ROOT / "environment/variables.tf"
    )


def test_staging_safety_validations_are_present():
    variables = text(STAGING / "variables.tf")
    required_guards = [
        'var.container_image_tag != "latest"',
        'regex("^[0-9a-f]{7,40}$"',
        'regex("^sha256:[0-9a-f]{64}$"',
        "!var.enable_local_auth",
        'var.stripe_mode == "test"',
        "var.artifact_bucket_name != var.production_artifact_bucket_name",
        "var.rds_identifier != var.production_rds_identifier",
        'check "network_selection"',
        'check "https_inputs"',
        'check "provider_boundaries"',
    ]
    for guard in required_guards:
        assert guard in variables


def test_production_mock_and_local_auth_flags_are_forced_off():
    variables = text(ROOT / "environment/variables.tf")
    for guard in (
        "!var.enable_local_auth",
        "!var.enable_mock_ai",
        "!var.enable_mock_payment",
        "!var.enable_mock_email",
    ):
        assert guard in variables


def test_staging_required_common_variables_are_declared():
    variables = text(STAGING / "variables.tf")
    required = {
        "environment", "name_prefix", "aws_account_id", "aws_region",
        "container_image_tag", "backend_image_repository",
        "worker_image_repository", "frontend_image_repository",
        "enable_local_auth", "enable_mock_ai", "enable_mock_payment",
        "enable_mock_email", "enable_cognito", "enable_stripe", "enable_ses",
        "enable_s3_storage", "log_retention_days", "desired_count_backend",
        "desired_count_worker", "desired_count_frontend", "db_instance_class",
        "db_multi_az", "backup_retention_days", "deletion_protection",
        "artifact_bucket_name", "domain_name", "route53_zone_id",
        "alarm_notification_email", "monthly_budget_amount",
    }
    declared = set(re.findall(r'variable "([^"]+)"', variables))
    assert required <= declared


def test_examples_contain_no_secret_values_or_fixed_resource_arns():
    examples = "\n".join(text(path) for path in STAGING.glob("*.example"))
    forbidden = ["sk_live_", "sk_test_", "whsec_", "AKIA", "BEGIN PRIVATE KEY"]
    assert not any(value in examples for value in forbidden)
    assert "arn:aws:" not in examples
    assert "REPLACE_WITH_UNIQUE_STAGING_BUCKET" in examples
    assert "<STAGING_STATE_KMS_KEY_ARN>" in examples


def test_secret_values_and_state_migration_are_not_managed():
    terraform = "\n".join(
        text(path)
        for base in (STAGING,)
        for path in base.rglob("*.tf")
    )
    terraform += "\n" + "\n".join(
        text(path)
        for base in (ROOT / "modules").glob("staging_*")
        for path in base.rglob("*.tf")
    )
    assert "aws_secretsmanager_secret_version" not in terraform
    assert not re.search(r"(?m)^\s*moved\s*\{", terraform)
    assert not re.search(r"(?m)^\s*import\s*\{", terraform)
    assert "AdministratorAccess" not in terraform


def test_staging_service_boundaries_and_migration_command():
    ecs = text(ROOT / "modules/staging_ecs/main.tf")
    assert 'command = ["uvicorn", "app.main:app"' in ecs
    assert 'command = ["python", "-m", "app.workers.runner"]' in ecs
    assert 'command = ["node", "server.js"]' in ecs
    assert 'command = ["alembic", "upgrade", "head"]' in ecs
    assert 'aws_iam_role.task["frontend"]' in ecs
    assert 'aws_iam_role.task["migration"]' in ecs
    assert "/system-navigator/staging/" in ecs
    layout = text(ROOT / "frontend/app/layout.tsx")
    assert "Mock Provider使用中" in layout
    assert "APP_ENABLE_MOCK_AI" in layout


def test_ignore_rules_cover_local_terraform_material():
    ignore = text(ROOT / ".gitignore")
    for pattern in (
        "**/backend.hcl", "**/terraform.tfvars", "*.tfstate",
        "*.tfstate.*", "*.tfplan", "**/.terraform/",
    ):
        assert pattern in ignore
