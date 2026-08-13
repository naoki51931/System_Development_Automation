variable "aws_account_id" {
  type        = string
  description = "クラウドAのAWSアカウントID"
}

variable "aws_region" {
  type        = string
  description = "AWSリージョン"
  default     = "eu-west-2"
}

variable "name" {
  type        = string
  description = "リソース名の接頭辞"
  default     = "ai-platform-prod"
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
