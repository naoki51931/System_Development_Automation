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
