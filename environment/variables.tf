variable "aws_account_id" {
  type        = string
  description = "クラウドAのAWSアカウントID"
  default     = "557604519341"
  validation {
    condition     = var.aws_account_id == "557604519341"
    error_message = "PRODUCTION_ACCOUNT_MISMATCH: Production is fixed to AWS account 557604519341."
  }
}

variable "aws_region" {
  type        = string
  description = "AWSリージョン"
  default     = "eu-west-2"
  validation {
    condition     = var.aws_region == "eu-west-2"
    error_message = "PRODUCTION_REGION_MISMATCH: Production is fixed to eu-west-2."
  }
}

variable "name" {
  type        = string
  description = "リソース名の接頭辞"
  default     = "ai-platform-prod"
  validation {
    condition     = var.name == "ai-platform-prod"
    error_message = "PRODUCTION_REPOSITORY_MISMATCH: Production resource prefix is fixed to ai-platform-prod."
  }
}

variable "container_image_tag" {
  type        = string
  description = "ECSで実行するコンテナイメージのタグ"
  default     = "v4"
  validation {
    condition     = var.container_image_tag != "latest"
    error_message = "The mutable latest tag is forbidden in production."
  }
}

variable "app_image_uri" {
  type        = string
  description = "Reviewed Production application image. Backend, worker, and migration share this exact ECR digest URI."

  validation {
    condition = can(regex(
      "^557604519341\\.dkr\\.ecr\\.eu-west-2\\.amazonaws\\.com/ai-platform-prod@sha256:[0-9a-f]{64}$",
      var.app_image_uri,
    ))
    error_message = "DIGEST_INPUT_UNSUPPORTED: app_image_uri must be the exact Production app ECR repository in this account/region pinned by @sha256. Tags, latest, malformed digests, and other repositories are forbidden."
  }
}

variable "frontend_image_uri" {
  type        = string
  description = "Reviewed Production frontend image pinned to the dedicated frontend ECR repository."

  validation {
    condition = can(regex(
      "^557604519341\\.dkr\\.ecr\\.eu-west-2\\.amazonaws\\.com/ai-platform-prod-frontend@sha256:[0-9a-f]{64}$",
      var.frontend_image_uri,
    ))
    error_message = "DIGEST_INPUT_UNSUPPORTED: frontend_image_uri must be the exact dedicated Production frontend ECR repository in this account/region pinned by @sha256."
  }
}

variable "enable_release_runtime" {
  type        = bool
  description = "Allows the digest-pinned backend/frontend/worker rollout only after the one-off migration has succeeded."
  default     = false
}

variable "migration_attestation" {
  type = object({
    release_sha                   = string
    ecs_cluster                   = string
    migration_task_arn            = string
    migration_task_definition     = string
    expected_app_image_uri        = string
    resolved_image_digest         = string
    task_stopped_reason           = string
    essential_container_exit_code = number
    expected_alembic_head         = string
    verified_alembic_head         = string
    verified_at                   = string
    artifact_sha256               = string
  })
  description = "Metadata from the read-only Production migration attestation verifier. Null is fail-closed for runtime rollout."
  default     = null
}

variable "external_launch_ready" {
  type        = bool
  description = "External launch remains blocked until Cognito, HTTPS/DNS, AI, payment, and email providers are separately connected and approved."
  default     = false
  validation {
    condition     = !var.external_launch_ready
    error_message = "PROVIDER_NOT_CONFIGURED: this remediation does not connect external launch providers and cannot declare external launch ready."
  }
}

check "migration_before_release_runtime" {
  assert {
    condition     = !var.enable_release_runtime || local.migration_attestation_valid
    error_message = "MIGRATION_SEQUENCE_UNSAFE: runtime requires a verifier-produced attestation for this digest, exit zero, and Alembic head 8d4f2a7c9b11."
  }
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR"
  default     = "10.20.0.0/16"
}

variable "artifact_bucket_name" {
  type        = string
  description = "成果物保存用S3バケット名"
}

variable "production_notification_email" {
  type        = string
  description = "Human-approved Production alarm email. Empty creates the isolated SNS topic and alarms without a subscription."
  default     = ""
  validation {
    condition     = var.production_notification_email == "" || can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.production_notification_email))
    error_message = "production_notification_email must be empty or a valid human-approved email address."
  }
}

variable "db_instance_class" {
  type        = string
  description = "RDSインスタンスクラス"
  default     = "db.t4g.medium"
}

variable "production_capacity_profile" {
  type        = string
  description = "Reviewed Production capacity profile. low-traffic targets 100 RPM steady and 600 RPM short burst."
  default     = "baseline"
  validation {
    condition     = contains(["baseline", "low-traffic"], var.production_capacity_profile)
    error_message = "production_capacity_profile must be baseline or low-traffic."
  }
}

variable "backend_cpu" {
  type        = number
  description = "Production backend Fargate CPU units."
  default     = 512
}

variable "backend_memory" {
  type        = number
  description = "Production backend Fargate memory in MiB."
  default     = 1024
}

variable "backend_desired_count" {
  type    = number
  default = 1
}

variable "backend_min_count" {
  type    = number
  default = 1
}

variable "backend_max_count" {
  type    = number
  default = 2
}

variable "backend_cpu_target" {
  type    = number
  default = 60
}

variable "backend_memory_target" {
  type    = number
  default = 70
}

check "production_capacity" {
  assert {
    condition = var.production_capacity_profile != "low-traffic" || (
      var.backend_cpu == 256 &&
      var.backend_memory == 512 &&
      var.backend_desired_count == 1 &&
      var.backend_min_count == 1 &&
      var.backend_max_count == 2 &&
      var.db_instance_class == "db.t4g.small"
    )
    error_message = "The reviewed low-traffic profile is 256 CPU, 512 MiB, desired/min 1, max 2, and db.t4g.small."
  }
  assert {
    condition     = var.backend_min_count <= var.backend_desired_count && var.backend_desired_count <= var.backend_max_count
    error_message = "Backend desired count must be between autoscaling min and max."
  }
}

variable "github_org" {
  type        = string
  description = "GitHub Organizationまたはユーザー名"
}

variable "github_repository" {
  type        = string
  description = "GitHubリポジトリ名"
}

# Production safety boundaries. These flags are intentionally not wired to the
# legacy production resources; true is rejected before any future provider work.
variable "enable_local_auth" {
  type        = bool
  description = "ProductionでLocalAuthを拒否する安全境界"
  default     = false
  validation {
    condition     = !var.enable_local_auth
    error_message = "LocalAuth is forbidden in production."
  }
}

variable "enable_mock_ai" {
  type        = bool
  description = "ProductionでMock AIを拒否する安全境界"
  default     = false
  validation {
    condition     = !var.enable_mock_ai
    error_message = "Mock AI is forbidden in production."
  }
}

variable "enable_mock_payment" {
  type        = bool
  description = "ProductionでMock paymentを拒否する安全境界"
  default     = false
  validation {
    condition     = !var.enable_mock_payment
    error_message = "Mock payment is forbidden in production."
  }
}

variable "enable_mock_email" {
  type        = bool
  description = "ProductionでMock emailを拒否する安全境界"
  default     = false
  validation {
    condition     = !var.enable_mock_email
    error_message = "Mock email is forbidden in production."
  }
}
