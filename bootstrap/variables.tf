variable "aws_account_id" {
  type        = string
  description = "クラウドAのAWSアカウントID"
}

variable "aws_region" {
  type        = string
  description = "AWSリージョン"
  default     = "ap-northeast-1"
}

variable "state_bucket_name" {
  type        = string
  description = "Terraform state保存用S3バケット名"
}

variable "lock_table_name" {
  type        = string
  description = "Terraform state lock用DynamoDBテーブル名"
  default     = "ai-platform-terraform-locks"
}
