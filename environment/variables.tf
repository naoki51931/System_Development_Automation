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

variable "db_instance_class" {
  type        = string
  description = "RDSインスタンスクラス"
  default     = "db.t4g.medium"
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
