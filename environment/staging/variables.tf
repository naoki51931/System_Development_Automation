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
    condition     = var.container_image_tag != "latest" && can(regex("^[0-9a-f]{7,40}$", var.container_image_tag))
    error_message = "Use a 7-40 character Git SHA; latest is forbidden. Runtime images are pinned separately by digest."
  }
}
variable "backend_image_uri" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$", var.backend_image_uri))
    error_message = "backend_image_uri must be a complete ECR URI pinned by sha256 digest."
  }
}
variable "worker_image_uri" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$", var.worker_image_uri))
    error_message = "worker_image_uri must be a complete ECR URI pinned by sha256 digest."
  }
}
variable "frontend_image_uri" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$", var.frontend_image_uri))
    error_message = "frontend_image_uri must be a complete ECR URI pinned by sha256 digest."
  }
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
variable "enable_runtime_services" {
  type        = bool
  description = "Create runtime ECS services only after database secret registration and migration."
  default     = false
}
variable "staging_mode" {
  type        = string
  description = "Staging cost mode. idle retains persistent/free foundations; active creates runtime infrastructure."
  default     = "active"
  validation {
    condition     = contains(["idle", "active"], var.staging_mode)
    error_message = "staging_mode must be idle or active."
  }
}
variable "idle_database_removal_approved" {
  type        = bool
  description = "Human approval gate for an idle apply that removes RDS. Keep false for review-only plans."
  default     = false
}
variable "idle_database_snapshot_identifier" {
  type        = string
  description = "Available manual snapshot protecting an approved idle RDS removal. Never commit a real identifier."
  default     = ""
}
variable "restore_db_from_snapshot" {
  type        = bool
  description = "Restore ACTIVE mode RDS from db_snapshot_identifier instead of creating an empty database."
  default     = false
}
variable "db_snapshot_identifier" {
  type        = string
  description = "Manual snapshot identifier used for ACTIVE restore; supply outside Git."
  default     = ""
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
  default = 3
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
variable "enable_custom_domain" {
  type        = bool
  description = "Enable a separately approved custom domain, ACM certificate and Route53 alias."
  default     = false
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
variable "prerequisite_sns_topic_arn" {
  type        = string
  description = "SNS topic ARN output from staging-prerequisites."
}
variable "prerequisite_github_deploy_role_arn" {
  type        = string
  description = "GitHub deploy role ARN output from staging-prerequisites."
}
variable "rds_connections_threshold" {
  type        = number
  description = "Alarm threshold below the safe connection limit for the selected staging DB class."
  default     = 80
  validation {
    condition     = var.rds_connections_threshold > 0
    error_message = "The RDS connections threshold must be positive."
  }
}
variable "rds_free_storage_threshold" {
  type        = number
  description = "FreeStorageSpace alarm threshold in bytes."
  default     = 5368709120
  validation {
    condition     = var.rds_free_storage_threshold > 0
    error_message = "The RDS free-storage threshold must be positive."
  }
}
variable "rds_freeable_memory_threshold" {
  type        = number
  description = "FreeableMemory alarm threshold in bytes for db.t4g.small."
  default     = 268435456
  validation {
    condition     = var.rds_freeable_memory_threshold > 0
    error_message = "The RDS freeable-memory threshold must be positive."
  }
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
variable "enable_nat_gateway" {
  type        = bool
  description = "Use one NAT gateway. Keep false while EIP quota is constrained."
  default     = false
}
variable "enable_interface_endpoints" {
  type        = bool
  description = "Create the seven paid Interface Endpoints in ACTIVE mode."
  default     = true
}
variable "enable_s3_gateway_endpoint" {
  type        = bool
  description = "Retain the no-hourly-charge S3 Gateway Endpoint in both modes."
  default     = true
}

variable "create_route53_record" {
  type        = bool
  description = "Create the staging alias record after the ALB exists."
  default     = false
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
check "network_selection" {
  assert {
    condition     = var.create_vpc ? (var.existing_vpc_id == "" && length(var.existing_private_subnet_ids) == 0 && length(var.existing_public_subnet_ids) == 0) : (var.existing_vpc_id != "" && length(var.existing_private_subnet_ids) >= 2 && length(var.existing_public_subnet_ids) >= 2)
    error_message = "Create exactly one network mode: a new VPC, or an existing VPC plus at least two public/private subnets."

  }
}
check "https_inputs" {
  assert {
    condition     = var.enable_custom_domain ? (var.enable_https && var.create_route53_record && var.domain_name != "" && var.route53_zone_id != "" && var.acm_certificate_arn != "") : (!var.enable_https && !var.create_route53_record && var.domain_name == "" && var.route53_zone_id == "" && var.acm_certificate_arn == "")
    error_message = "Custom domains require HTTPS, Route53 and ACM inputs; disabled custom domains require all domain settings to remain off and empty."
  }
}
check "image_identity" {
  assert {
    condition     = var.backend_image_uri == var.worker_image_uri
    error_message = "Backend and worker must use the same reviewed application image digest."
  }
  assert {
    condition     = startswith(var.backend_image_uri, "${var.aws_account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/") && startswith(var.frontend_image_uri, "${var.aws_account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/")
    error_message = "Staging images must come from the configured account and region."
  }
}
check "mode_boundaries" {
  assert {
    condition     = var.staging_mode == "active" || !var.enable_runtime_services
    error_message = "Runtime services cannot be enabled in idle mode."
  }
  assert {
    condition     = var.staging_mode == "active" || !var.enable_nat_gateway
    error_message = "Idle mode must not create a NAT Gateway."
  }
}
check "snapshot_restore_inputs" {
  assert {
    condition     = var.restore_db_from_snapshot == (var.db_snapshot_identifier != "")
    error_message = "restore_db_from_snapshot and db_snapshot_identifier must be enabled/provided together."
  }
  assert {
    condition     = var.staging_mode == "active" || !var.restore_db_from_snapshot
    error_message = "Snapshot restore is valid only in active mode."
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
