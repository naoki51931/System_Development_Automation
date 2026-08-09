provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.aws_account_id]
  default_tags {
    tags = {
      Application = "SystemNavigator AI"
      Environment = "staging"
      ManagedBy   = "Terraform"
      GitCommit   = var.container_image_tag
    }
  }
}

module "ecr" {
  source               = "../../modules/staging_ecr"
  repository_names     = var.repository_names
  retain_tagged_images = var.retain_tagged_images
}

module "deploy_role" {
  source                   = "../../modules/staging_deploy_role"
  name_prefix              = var.name_prefix
  aws_account_id           = var.aws_account_id
  aws_region               = var.aws_region
  github_oidc_provider_arn = var.github_oidc_provider_arn
  github_org               = var.github_org
  github_repository        = var.github_repository
  github_environment       = var.github_environment
  ecr_repository_arns      = values(module.ecr.repository_arns)
  state_bucket_name        = var.state_bucket_name
  state_kms_key_arn        = var.state_kms_key_arn
}

module "dns" {
  count           = var.enable_custom_domain ? 1 : 0
  source          = "../../modules/staging_dns"
  domain_name     = var.domain_name
  route53_zone_id = var.route53_zone_id
}

module "notifications" {
  source                   = "../../modules/staging_notifications"
  name_prefix              = var.name_prefix
  alarm_notification_email = var.alarm_notification_email
  monthly_budget_amount    = var.monthly_budget_amount
  budget_currency          = var.budget_currency
}
