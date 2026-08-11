from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_BACKEND = ROOT / "environment/backend.hcl.example"
STAGING = ROOT / "environment/staging"
PREREQUISITES = ROOT / "environment/staging-prerequisites"


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
    assert 'default     = "ai-platform-prod"' in text(ROOT / "environment/variables.tf")


def test_staging_safety_validations_are_present():
    variables = text(STAGING / "variables.tf")
    required_guards = [
        'var.container_image_tag != "latest"',
        'regex("^[0-9a-f]{7,40}$"',
        'check "image_identity"',
        "@sha256:[0-9a-f]{64}",
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
    assert 'var.container_image_tag != "latest"' in variables


def test_staging_required_common_variables_are_declared():
    variables = text(STAGING / "variables.tf")
    required = {
        "environment",
        "name_prefix",
        "aws_account_id",
        "aws_region",
        "container_image_tag",
        "backend_image_uri",
        "worker_image_uri",
        "frontend_image_uri",
        "enable_local_auth",
        "enable_mock_ai",
        "enable_mock_payment",
        "enable_mock_email",
        "enable_cognito",
        "enable_stripe",
        "enable_ses",
        "enable_s3_storage",
        "log_retention_days",
        "desired_count_backend",
        "desired_count_worker",
        "desired_count_frontend",
        "enable_runtime_services",
        "staging_mode",
        "idle_database_removal_approved",
        "allow_database_deletion",
        "idle_database_snapshot_identifier",
        "restore_db_from_snapshot",
        "db_snapshot_identifier",
        "db_instance_class",
        "db_multi_az",
        "backup_retention_days",
        "deletion_protection",
        "artifact_bucket_name",
        "enable_custom_domain",
        "domain_name",
        "route53_zone_id",
        "prerequisite_sns_topic_arn",
        "prerequisite_github_deploy_role_arn",
        "rds_connections_threshold",
        "rds_free_storage_threshold",
        "rds_freeable_memory_threshold",
    }
    declared = set(re.findall(r'variable "([^"]+)"', variables))
    assert required <= declared


def test_examples_contain_no_secret_values_or_fixed_resource_arns():
    examples = "\n".join(text(path) for path in STAGING.glob("*.example"))
    forbidden = ["sk_live_", "sk_test_", "whsec_", "AKIA", "BEGIN " + "PRIVATE KEY"]
    assert not any(value in examples for value in forbidden)
    assert "arn:aws:" not in examples
    assert "REPLACE_WITH_UNIQUE_STAGING_BUCKET" in examples
    assert "<STAGING_STATE_KMS_KEY_ARN>" in examples


def test_secret_values_and_state_migration_are_not_managed():
    terraform = "\n".join(
        text(path) for base in (STAGING,) for path in base.rglob("*.tf")
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
    assert 'role = aws_iam_role.task["frontend"].id' not in ecs
    assert "/system-navigator/staging/" in ecs
    layout = text(ROOT / "frontend/app/layout.tsx")
    assert "Mock Provider使用中" in layout
    assert "APP_ENABLE_MOCK_AI" in layout


def test_staging_health_paths_are_service_specific():
    ecs = text(ROOT / "modules/staging_ecs/main.tf")
    assert 'path    = "/health"' in ecs
    assert 'path    = "/login"' in ecs
    assert "http://localhost:8000/health" in ecs
    assert "http://localhost:3000/login" in ecs
    assert "http://localhost:3000/ || exit 1" not in ecs


def test_staging_runtime_services_and_alarms_are_bootstrap_gated():
    variables = text(STAGING / "variables.tf")
    example = text(STAGING / "terraform.tfvars.example")
    ecs = text(ROOT / "modules/staging_ecs/main.tf")
    monitoring = text(ROOT / "modules/staging_monitoring/main.tf")
    assert 'variable "enable_runtime_services"' in variables
    assert "enable_runtime_services = false" in example
    assert 'variable "enable_runtime_infrastructure"' in ecs
    assert ecs.count("var.enable_runtime_infrastructure && var.enable_runtime_services ? 1 : 0") == 3
    for service in ("backend", "worker", "frontend"):
        block = re.search(
            rf'resource "aws_ecs_service" "{service}" \{{(.*?)\n\}}', ecs, re.S
        )
        assert block and "var.enable_runtime_infrastructure && var.enable_runtime_services ? 1 : 0" in block.group(1)
    assert 'resource "aws_ecs_task_definition" "migration"' in ecs
    assert 'command = ["alembic", "upgrade", "head"]' in ecs
    assert "aws_secretsmanager_secret_version" not in ecs
    assert "service_dimensions = var.enabled && var.enable_runtime_services ?" in monitoring
    assert "for_each = var.enabled && var.enable_runtime_services ?" in monitoring
    assert monitoring.count("var.enabled && var.enable_runtime_services") >= 3


def test_idle_mode_removes_costly_runtime_and_preserves_foundations():
    root = text(STAGING / "main.tf")
    variables = text(STAGING / "variables.tf")
    outputs = text(STAGING / "outputs.tf")
    network = text(ROOT / "modules/staging_network/main.tf")
    database = text(ROOT / "modules/staging_database/main.tf")
    ecs = text(ROOT / "modules/staging_ecs/main.tf")
    storage = text(ROOT / "modules/staging_storage/main.tf")

    assert 'default     = "active"' in variables
    assert 'contains(["idle", "active"], var.staging_mode)' in variables
    assert 'active_mode = var.staging_mode == "active"' in root
    assert "enable_interface_endpoints = local.active_mode && var.enable_interface_endpoints" in root
    assert "enable_s3_gateway_endpoint = var.enable_s3_gateway_endpoint" in root
    assert 'count                           = var.enabled ? 1 : 0' in database
    assert "enable_runtime_infrastructure   = local.active_mode" in root
    assert 'count = var.enable_runtime_infrastructure ? 1 : 0' in ecs
    assert 'for_each          = toset(["backend", "worker", "frontend", "migration"])' in ecs
    assert 'count             = var.create_vpc && var.enable_s3_gateway_endpoint ? 1 : 0' in network
    assert 'prevent_destroy = true' in storage
    assert 'output "idle_cost_resource_counts"' in outputs


def test_idle_rds_apply_and_snapshot_restore_fail_closed():
    root = text(STAGING / "main.tf")
    variables = text(STAGING / "variables.tf")
    database = text(ROOT / "modules/staging_database/main.tf")

    assert 'data "aws_db_snapshot" "idle_removal"' in root
    assert 'resource "terraform_data" "idle_apply_gate"' in root
    assert "RDS_IDLE_REMOVAL blocked" in root
    assert "idle_database_removal_approved" in variables
    assert 'variable "allow_database_deletion"' in variables
    assert 'default     = false' in variables
    assert 'check "database_deletion_approval"' in variables
    assert 'var.staging_mode == "active"' in variables
    assert 'var.idle_database_removal_approved' in variables
    assert 'var.idle_database_snapshot_identifier != ""' in variables
    assert 'try(data.aws_db_snapshot.idle_removal[0].status == "available", false)' in variables
    assert 'deletion_protection   = var.deletion_protection && !var.allow_database_deletion' in root
    assert 'var.restore_db_from_snapshot == (var.db_snapshot_identifier != "")' in variables
    assert "snapshot_identifier             = var.snapshot_identifier" in database
    assert 'db_name                         = var.snapshot_identifier == null ? "systemnavigator" : null' in database
    assert "prevent_destroy" not in database


def test_production_root_has_no_idle_mode_references():
    production = "\n".join(text(path) for path in (ROOT / "environment").glob("*.tf"))
    for token in (
        "staging_mode",
        "idle_database_removal_approved",
        "allow_database_deletion",
        "enable_interface_endpoints",
        "restore_db_from_snapshot",
    ):
        assert token not in production


def test_staging_service_discovery_avoids_unstable_empty_custom_health_check():
    ecs = text(ROOT / "modules/staging_ecs/main.tf")
    discovery = re.search(
        r'resource "aws_service_discovery_service" "internal" \{(.*?)\n\}', ecs, re.S
    )
    assert discovery
    assert (
        'for_each = var.enable_runtime_infrastructure ? toset(["backend", "worker"]) : toset([])'
        in discovery.group(1)
    )
    assert 'routing_policy = "MULTIVALUE"' in discovery.group(1)
    assert 'type = "A"' in discovery.group(1)
    assert "health_check_custom_config" not in discovery.group(1)
    assert "ignore_changes" not in discovery.group(1)


def test_preplan_resources_are_scoped_and_private():
    ecr = text(ROOT / "modules/staging_ecr/main.tf")
    deploy = text(ROOT / "modules/staging_deploy_role/main.tf")
    network = text(ROOT / "modules/staging_network/main.tf")
    dns = text(ROOT / "modules/staging_dns/main.tf")
    assert 'image_tag_mutability = "IMMUTABLE"' in ecr
    assert "scan_on_push = true" in ecr
    assert "aws_ecr_lifecycle_policy" in ecr
    assert "environment:${var.github_environment}" in deploy
    assert "repo:${var.github_org}/${var.github_repository}:*" not in deploy
    assert "AdministratorAccess" not in deploy
    assert "aws_vpc_endpoint" in network
    assert '"ecr.api"' in network and '"secretsmanager"' in network
    assert "aws_acm_certificate_validation" in dns
    assert "aws_route53_record" in dns


def test_ignore_rules_cover_local_terraform_material():
    ignore = text(ROOT / ".gitignore")
    for pattern in (
        "**/backend.hcl",
        "**/terraform.tfvars",
        "*.tfstate",
        "*.tfstate.*",
        "*.tfplan",
        "**/.terraform/",
    ):
        assert pattern in ignore


def test_staging_monitoring_matches_approved_notification_policy():
    monitoring = text(ROOT / "modules/staging_monitoring/main.tf")
    notifications = text(ROOT / "modules/staging_notifications/main.tf")
    example = text(PREREQUISITES / "terraform.tfvars.example")
    ecs = text(ROOT / "modules/staging_ecs/main.tf")
    for metric in (
        "HTTPCode_ELB_5XX_Count",
        "UnHealthyHostCount",
        "TargetResponseTime",
        "CPUUtilization",
        "MemoryUtilization",
        "RunningTaskCount",
        "WorkerHeartbeatAgeSeconds",
        "DeadLetterCount",
        "DatabaseConnections",
        "FreeStorageSpace",
        "FreeableMemory",
    ):
        assert metric in monitoring
    assert 'name = "${var.name_prefix}-alerts"' in notifications
    assert 'protocol  = "email"' in notifications
    assert "subscriber_email_addresses" in notifications
    assert 'alarm_notification_email = "REPLACE_WITH_NOTIFICATION_EMAIL"' in example
    assert "info@nagi-neco.com" not in example
    assert "monthly_budget_amount     = 150" in example
    assert 'budget_currency           = "USD"' in example
    assert "enable_budget             = false" in example
    assert 'name  = "containerInsights"' in ecs


def test_prerequisite_root_is_complete_and_isolated():
    root_tf = "\n".join(text(path) for path in PREREQUISITES.glob("*.tf"))
    modules = "\n".join(
        text(path)
        for module in (
            "staging_ecr",
            "staging_deploy_role",
            "staging_dns",
            "staging_notifications",
        )
        for path in (ROOT / "modules" / module).glob("*.tf")
    )
    combined = root_tf + modules
    backend = text(PREREQUISITES / "backend.hcl.example")
    assert 'key          = "system-navigator/staging/prerequisites.tfstate"' in backend
    assert "cloud-a/prod/terraform.tfstate" not in backend
    assert "system-navigator/staging/terraform.tfstate" not in backend
    for resource in (
        "aws_db_instance",
        "aws_ecs_cluster",
        "aws_ecs_service",
        "aws_lb ",
        "aws_vpc ",
        "aws_subnet",
        "aws_secretsmanager_secret",
        "aws_s3_bucket",
        "terraform_remote_state",
    ):
        assert resource not in combined
    for required in (
        'module "ecr"',
        'module "deploy_role"',
        'module "dns"',
        'module "notifications"',
    ):
        assert required in root_tf


def test_prerequisite_trust_budget_dns_and_outputs_are_safe():
    deploy = text(ROOT / "modules/staging_deploy_role/main.tf")
    dns = text(ROOT / "modules/staging_dns/main.tf")
    notifications = text(ROOT / "modules/staging_notifications/main.tf")
    variables = text(PREREQUISITES / "variables.tf")
    outputs = text(PREREQUISITES / "outputs.tf")
    assert "sts.amazonaws.com" in deploy
    assert "environment:${var.github_environment}" in deploy
    assert 'actions   = ["iam:PassRole"]' in deploy
    assert "role/${var.name_prefix}-*" in deploy
    assert "ai-platform-prod" not in deploy
    assert "AdministratorAccess" not in deploy
    assert "aws_acm_certificate_validation" in dns
    assert "var.domain_name" in dns and "var.route53_zone_id" in dns
    assert 'variable "enable_custom_domain"' in variables
    assert '!var.enable_custom_domain || can(regex("^staging\\\\."' in variables
    assert 'default = "USD"' in variables
    assert 'var.budget_currency == "USD"' in variables
    assert "default = 150" in variables
    assert "var.monthly_budget_amount == 150" in variables
    assert notifications.count('type = "ACTUAL"') == 3
    assert notifications.count('type = "FORECASTED"') == 1
    assert "var.alarm_notification_email" in notifications
    assert "count        = var.enable_budget ? 1 : 0" in notifications
    assert "try(aws_budgets_budget.monthly[0].name, null)" in notifications
    for name in (
        "app_ecr_repository_url",
        "frontend_ecr_repository_url",
        "github_deploy_role_arn",
        "acm_certificate_arn",
        "sns_topic_arn",
        "alert_email_address",
        "budget_name",
    ):
        assert f'output "{name}"' in outputs


def test_custom_domain_is_disabled_without_removing_other_prerequisites():
    prerequisite_main = text(PREREQUISITES / "main.tf")
    prerequisite_vars = text(PREREQUISITES / "variables.tf")
    prerequisite_example = text(PREREQUISITES / "terraform.tfvars.example")
    staging_vars = text(STAGING / "variables.tf")
    staging_dns = text(STAGING / "dns.tf")
    staging_example = text(STAGING / "terraform.tfvars.example")
    notifications = text(ROOT / "modules/staging_notifications/main.tf")

    assert "count           = var.enable_custom_domain ? 1 : 0" in prerequisite_main
    assert 'variable "enable_custom_domain"' in prerequisite_vars
    assert "default     = false" in prerequisite_vars
    assert "enable_custom_domain = false" in prerequisite_example
    assert 'domain_name          = ""' in prerequisite_example
    assert 'route53_zone_id      = ""' in prerequisite_example
    assert 'variable "enable_custom_domain"' in staging_vars
    assert "var.enable_custom_domain && var.enable_https" in staging_dns
    assert "enable_custom_domain  = false" in staging_example
    assert "enable_https          = false" in staging_example
    assert "create_route53_record = false" in staging_example
    assert 'module "ecr"' in prerequisite_main
    assert 'module "deploy_role"' in prerequisite_main
    assert 'module "notifications"' in prerequisite_main
    assert 'name = "${var.name_prefix}-alerts"' in notifications
    assert notifications.count('type = "ACTUAL"') == 3
    assert notifications.count('type = "FORECASTED"') == 1


def test_deprecated_domain_has_no_active_configuration_reference():
    active_paths = [
        *PREREQUISITES.glob("*.tf"),
        PREREQUISITES / "terraform.tfvars.example",
        *STAGING.glob("*.tf"),
        STAGING / "terraform.tfvars.example",
    ]
    assert all("true-camera-test" not in text(path) for path in active_paths)
