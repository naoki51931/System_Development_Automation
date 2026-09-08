from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "environment/staging"
PREREQUISITES = ROOT / "environment/staging-prerequisites"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_approved_domain_and_external_dns_are_defaults():
    staging_vars = read(STAGING / "variables.tf")
    prerequisite_vars = read(PREREQUISITES / "variables.tf")
    examples = read(STAGING / "terraform.tfvars.example") + read(
        PREREQUISITES / "terraform.tfvars.example"
    )
    assert examples.count('domain_name          = "test.system-navigation.com"') >= 1
    assert staging_vars.count('default = "test.system-navigation.com"') == 1
    assert prerequisite_vars.count('default = "test.system-navigation.com"') == 1
    assert examples.count('dns_provider         = "external"') >= 1


def test_external_dns_creates_zero_route53_records():
    module = read(ROOT / "modules/staging_dns/main.tf")
    alias = read(STAGING / "dns.tf")
    assert 'for_each = var.dns_provider == "route53" ? {' in module
    assert 'count                   = var.dns_provider == "route53" ? 1 : 0' in module
    assert 'var.dns_provider == "route53" && var.create_route53_record' in alias


def test_acm_uses_dns_validation_and_exports_manual_records():
    module = read(ROOT / "modules/staging_dns/main.tf")
    outputs = read(PREREQUISITES / "outputs.tf")
    assert 'validation_method = "DNS"' in module
    assert 'output "staging_acm_validation_records"' in outputs
    for field in ("domain", "name", "type", "value"):
        assert f"{field}" in module
    assert "option.domain_name" in module
    assert "option.resource_record_name" in module
    assert "option.resource_record_type" in module
    assert "option.resource_record_value" in module


def test_idle_default_preserves_zero_runtime_resources():
    variables = read(STAGING / "variables.tf")
    outputs = read(STAGING / "outputs.tf")
    main = read(STAGING / "main.tf")
    assert 'description = "Staging cost mode.' in variables
    staging_block = variables.split('variable "staging_mode"', 1)[1].split("}\n", 1)[0]
    assert 'default     = "idle"' in staging_block
    assert "rds                 = local.active_mode ? 1 : 0" in outputs
    assert "alb                 = local.active_mode ? 1 : 0" in outputs
    assert (
        "runtime_services    = local.active_mode && var.enable_runtime_services ? 3 : 0"
        in outputs
    )
    assert "enabled               = local.active_mode" in main
    assert "enable_runtime_infrastructure   = local.active_mode" in main


def test_active_https_redirect_and_readiness_gates_are_present():
    ecs = read(ROOT / "modules/staging_ecs/main.tf")
    variables = read(STAGING / "variables.tf")
    assert 'resource "aws_lb_listener" "https"' in ecs
    assert "port              = 443" in ecs
    assert 'type = "redirect"' in ecs
    assert 'status_code = "HTTP_301"' in ecs
    assert 'var.acm_certificate_arn != "" && var.acm_certificate_issued' in variables
    assert 'var.staging_mode == "idle" || var.allow_staging_reactivation' in variables


def test_domain_outputs_origin_and_relative_frontend_api():
    outputs = read(STAGING / "outputs.tf")
    ecs = read(ROOT / "modules/staging_ecs/main.tf")
    main = read(STAGING / "main.tf")
    dockerfile = read(ROOT / "frontend/Dockerfile")
    assert 'output "staging_alb_dns_name"' in outputs
    assert 'name = "APP_FRONTEND_ORIGIN", value = var.frontend_origin' in ecs
    assert 'frontend_origin                 = "https://${var.domain_name}"' in main
    assert "ARG NEXT_PUBLIC_API_BASE_URL=/api/v1" in dockerfile


def test_deprecated_domain_has_zero_active_refs_and_production_is_untouched():
    active = [
        *STAGING.glob("*.tf"),
        STAGING / "terraform.tfvars.example",
        *PREREQUISITES.glob("*.tf"),
        PREREQUISITES / "terraform.tfvars.example",
    ]
    assert all("true-camera-test.com" not in read(path) for path in active)
    # Domain implementation stays in staging-only roots/modules.
    assert "test.system-navigation.com" not in read(ROOT / "environment/main.tf")
    assert "test.system-navigation.com" not in read(ROOT / "environment/variables.tf")
