provider "aws" {
  region              = local.production_region
  allowed_account_ids = [local.production_account_id]

  default_tags {
    tags = {
      System      = "ai-development-platform"
      Environment = "prod"
      Cloud       = "cloud-a"
      ManagedBy   = "terraform"
    }
  }
}

locals {
  production_account_id          = "557604519341"
  production_region              = "eu-west-2"
  production_app_repository      = "ai-platform-prod"
  production_frontend_repository = "ai-platform-prod-frontend"
  migration_attestation_valid = var.migration_attestation != null && (
    try(var.migration_attestation.expected_app_image_uri, "") == var.app_image_uri &&
    try(var.migration_attestation.resolved_image_digest, "") == try(split("@", var.app_image_uri)[1], "") &&
    try(var.migration_attestation.essential_container_exit_code, -1) == 0 &&
    try(var.migration_attestation.expected_alembic_head, "") == "8d4f2a7c9b11" &&
    try(var.migration_attestation.verified_alembic_head, "") == "8d4f2a7c9b11" &&
    try(var.migration_attestation.ecs_cluster, "") == "arn:aws:ecs:eu-west-2:557604519341:cluster/ai-platform-prod" &&
    try(var.migration_attestation.task_stopped_reason, "") != "" &&
    can(regex("^[0-9a-f]{40}$", try(var.migration_attestation.release_sha, ""))) &&
    can(regex("^arn:aws:ecs:eu-west-2:557604519341:task/ai-platform-prod/[0-9a-f]{32}$", try(var.migration_attestation.migration_task_arn, ""))) &&
    can(regex("^arn:aws:ecs:eu-west-2:557604519341:task-definition/ai-platform-prod-migration:[1-9][0-9]*$", try(var.migration_attestation.migration_task_definition, ""))) &&
    can(formatdate("YYYY-MM-DD'T'hh:mm:ssZ", try(var.migration_attestation.verified_at, ""))) &&
    can(regex("^[0-9a-f]{64}$", try(var.migration_attestation.artifact_sha256, "")))
  )
}

resource "terraform_data" "release_runtime_gate" {
  input = var.enable_release_runtime

  lifecycle {
    precondition {
      condition     = !var.enable_release_runtime || local.migration_attestation_valid
      error_message = "MIGRATION_SEQUENCE_UNSAFE: verified migration attestation is required before any release runtime rollout."
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
  source                 = "../modules/ecs"
  name                   = local.production_app_repository
  vpc_id                 = module.network.vpc_id
  public_subnet_ids      = module.network.public_subnet_ids
  private_subnet_ids     = module.network.private_subnet_ids
  bucket_arn             = module.storage.bucket_arn
  image_tag              = var.container_image_tag
  app_image              = var.app_image_uri
  frontend_image         = var.frontend_image_uri
  aws_region             = local.production_region
  database_secret_arn    = module.database.secret_arn
  enable_release_runtime = var.enable_release_runtime
  release_gate_approved  = local.migration_attestation_valid
  capacity_profile       = var.production_capacity_profile
  backend_cpu            = var.backend_cpu
  backend_memory         = var.backend_memory
  desired_count          = var.backend_desired_count
  min_count              = var.backend_min_count
  max_count              = var.backend_max_count
  cpu_target             = var.backend_cpu_target
  memory_target          = var.backend_memory_target
  depends_on             = [terraform_data.release_runtime_gate]
}

module "database" {
  source              = "../modules/database"
  name                = var.name
  instance_class      = var.db_instance_class
  database_subnet_ids = module.network.database_subnet_ids
  application_sg_id   = module.ecs.application_sg_id
}

module "monitoring" {
  source                    = "../modules/production_monitoring"
  name                      = var.name
  notification_email        = var.production_notification_email
  alb_arn_suffix            = module.ecs.alb_arn_suffix
  target_group_arn_suffix   = module.ecs.target_group_arn_suffix
  ecs_cluster_name          = module.ecs.ecs_cluster_name
  ecs_service_name          = module.ecs.ecs_service_name
  frontend_service_name     = module.ecs.frontend_service_name
  worker_service_name       = module.ecs.worker_service_name
  desired_task_count        = var.backend_desired_count
  worker_desired_task_count = 1
  release_runtime_enabled   = var.enable_release_runtime
  db_instance_identifier    = module.database.db_instance_identifier
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
