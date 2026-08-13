provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = {
      System      = "ai-development-platform"
      Environment = "prod"
      Cloud       = "cloud-a"
      ManagedBy   = "terraform"
    }
  }
}

module "network" {
  source   = "../modules/network"
  name     = var.name
  vpc_cidr = var.vpc_cidr
}

module "storage" {
  source      = "../modules/storage"
  bucket_name = var.artifact_bucket_name
}

module "ecs" {
  source             = "../modules/ecs"
  name               = var.name
  vpc_id             = module.network.vpc_id
  public_subnet_ids  = module.network.public_subnet_ids
  private_subnet_ids = module.network.private_subnet_ids
  bucket_arn         = module.storage.bucket_arn
  image_tag          = var.container_image_tag
  capacity_profile   = var.production_capacity_profile
  backend_cpu        = var.backend_cpu
  backend_memory     = var.backend_memory
  desired_count      = var.backend_desired_count
  min_count          = var.backend_min_count
  max_count          = var.backend_max_count
  cpu_target         = var.backend_cpu_target
  memory_target      = var.backend_memory_target
}

module "database" {
  source              = "../modules/database"
  name                = var.name
  instance_class      = var.db_instance_class
  database_subnet_ids = module.network.database_subnet_ids
  application_sg_id   = module.ecs.application_sg_id
}

module "monitoring" {
  source                  = "../modules/production_monitoring"
  name                    = var.name
  notification_email      = var.production_notification_email
  alb_arn_suffix          = module.ecs.alb_arn_suffix
  target_group_arn_suffix = module.ecs.target_group_arn_suffix
  ecs_cluster_name        = module.ecs.ecs_cluster_name
  ecs_service_name        = module.ecs.ecs_service_name
  desired_task_count      = var.backend_desired_count
  db_instance_identifier  = module.database.db_instance_identifier
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_policy_document" "github_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repository}:*"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = "${var.name}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_trust.json
}
