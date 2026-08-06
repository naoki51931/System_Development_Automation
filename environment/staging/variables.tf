variable "environment" {
  type    = string
  default = "staging"
  validation {
    condition     = var.environment == "staging"
    error_message = "This root is staging-only."
  }
}
variable "name_prefix" {
  type    = string
  default = "system-navigator-staging"
  validation {
    condition     = can(regex("staging", var.name_prefix)) && var.name_prefix != "ai-platform-prod"
    error_message = "The staging prefix must contain staging and differ from production."
  }
}
variable "aws_account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain 12 digits."
  }
}
variable "aws_region" {
  type    = string
  default = "eu-west-2"
}
variable "container_image_tag" {
  type    = string
  default = "57109fa"
  validation {
    condition     = var.container_image_tag != "latest" && (can(regex("^[0-9a-f]{7,40}$", var.container_image_tag)) || can(regex("^sha256:[0-9a-f]{64}$", var.container_image_tag)))
    error_message = "Use a 7-40 character Git SHA or sha256 image digest; latest is forbidden."
  }
}
variable "backend_image_repository" {
  type = string
}
variable "worker_image_repository" {
  type = string
}
variable "frontend_image_repository" {
  type = string
}

variable "enable_local_auth" {
  type    = bool
  default = false
  validation {
    condition     = !var.enable_local_auth
    error_message = "LocalAuth is forbidden in staging."
  }
}
variable "enable_mock_ai" {
  type    = bool
  default = true
}
variable "enable_mock_payment" {
  type    = bool
  default = true
}
variable "enable_mock_email" {
  type    = bool
  default = true
}
variable "enable_cognito" {
  type    = bool
  default = false
}
variable "enable_stripe" {
  type    = bool
  default = false
}
variable "enable_ses" {
  type    = bool
  default = false
}
variable "enable_s3_storage" {
  type    = bool
  default = true
}
variable "stripe_mode" {
  type    = string
  default = "test"
  validation {
    condition     = var.stripe_mode == "test"
    error_message = "Staging only permits Stripe test mode."
  }
}

variable "log_retention_days" {
  type    = number
  default = 14
}
variable "desired_count_backend" {
  type    = number
  default = 1
}
variable "desired_count_worker" {
  type    = number
  default = 1
}
variable "desired_count_frontend" {
  type    = number
  default = 1
}
variable "db_instance_class" {
  type    = string
  default = "db.t4g.small"
}
variable "db_multi_az" {
  type    = bool
  default = false
}
variable "backup_retention_days" {
  type    = number
  default = 7
}
variable "deletion_protection" {
  type    = bool
  default = true
}

variable "artifact_bucket_name" {
  type = string
  validation {
    condition     = can(regex("staging", var.artifact_bucket_name)) && var.artifact_bucket_name != var.production_artifact_bucket_name
    error_message = "The bucket must be staging-specific and differ from production."
  }
}
variable "production_artifact_bucket_name" {
  type    = string
  default = "REPLACE_WITH_PRODUCTION_BUCKET_NAME"
}
variable "rds_identifier" {
  type    = string
  default = "system-navigator-staging-db"
  validation {
    condition     = can(regex("staging", var.rds_identifier)) && var.rds_identifier != var.production_rds_identifier
    error_message = "The RDS identifier must be staging-specific and differ from production."
  }
}
variable "production_rds_identifier" {
  type    = string
  default = "ai-platform-prod-postgres"
}

variable "domain_name" {
  type    = string
  default = ""
}
variable "route53_zone_id" {
  type    = string
  default = ""
}
variable "acm_certificate_arn" {
  type    = string
  default = ""
}
variable "enable_https" {
  type    = bool
  default = false
}
variable "alarm_notification_email" {
  type      = string
  default   = ""
  sensitive = true
}
variable "monthly_budget_amount" {
  type    = number
  default = 100
}

variable "create_vpc" {
  type    = bool
  default = true
}
variable "existing_vpc_id" {
  type    = string
  default = ""
}
variable "existing_private_subnet_ids" {
  type    = list(string)
  default = []
}
variable "existing_public_subnet_ids" {
  type    = list(string)
  default = []
}
variable "vpc_cidr" {
  type    = string
  default = "10.30.0.0/16"
}

variable "cognito_user_pool_id" {
  type    = string
  default = ""
}
variable "cognito_app_client_id" {
  type    = string
  default = ""
}
variable "cognito_issuer" {
  type    = string
  default = ""
}
variable "cognito_domain" {
  type    = string
  default = ""
}
variable "stripe_secret_key_secret_arn" {
  type      = string
  default   = ""
  sensitive = true
}
variable "stripe_webhook_secret_arn" {
  type      = string
  default   = ""
  sensitive = true
}
variable "stripe_publishable_key" {
  type    = string
  default = ""
}
variable "stripe_webhook_endpoint" {
  type    = string
  default = ""
}
variable "ses_region" {
  type    = string
  default = "eu-west-2"
}
variable "ses_from_address" {
  type    = string
  default = ""
}
variable "ses_configuration_set" {
  type    = string
  default = ""
}
variable "ses_sandbox_mode" {
  type    = bool
  default = true
}
variable "github_oidc_provider_arn" {
  type = string
}
variable "github_org" {
  type = string
}
variable "github_repository" {
  type = string
}

check "network_selection" {
  assert {
    condition     = var.create_vpc ? (var.existing_vpc_id == "" && length(var.existing_private_subnet_ids) == 0 && length(var.existing_public_subnet_ids) == 0) : (var.existing_vpc_id != "" && length(var.existing_private_subnet_ids) >= 2 && length(var.existing_public_subnet_ids) >= 2)
    error_message = "Create exactly one network mode: a new VPC, or an existing VPC plus at least two public/private subnets."

  }
}
check "https_inputs" {
  assert {
    condition     = !var.enable_https || (var.acm_certificate_arn != "" && var.domain_name != "" && var.route53_zone_id != "")
    error_message = "HTTPS requires an ACM certificate, domain name, and Route53 zone."
  }
}
check "provider_boundaries" {
  assert {
    condition     = !var.enable_cognito || (var.cognito_user_pool_id != "" && var.cognito_app_client_id != "" && var.cognito_issuer != "")
    error_message = "Enabled Cognito requires pool, app client, and issuer inputs."
  }
  assert {
    condition     = !var.enable_stripe || (var.stripe_secret_key_secret_arn != "" && var.stripe_webhook_secret_arn != "" && can(regex("^https://", var.stripe_webhook_endpoint)))
    error_message = "Enabled Stripe requires secret ARNs and an HTTPS webhook endpoint."
  }
  assert {
    condition     = !var.enable_ses || (var.ses_from_address != "" && var.ses_sandbox_mode)
    error_message = "Staging SES requires a from address and sandbox mode."
  }
}
