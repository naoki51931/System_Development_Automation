provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.aws_account_id]
  default_tags {
    tags = {
      Application = "SystemNavigator AI"
      Environment = var.environment
      ManagedBy   = "Terraform"
      GitCommit   = var.container_image_tag
    }
  }
}

module "network" {
  source               = "../../modules/staging_network"
  create_vpc           = var.create_vpc
  name_prefix          = var.name_prefix
  vpc_cidr             = var.vpc_cidr
  aws_region           = var.aws_region
  enable_nat_gateway   = var.enable_nat_gateway
  enable_vpc_endpoints = var.enable_vpc_endpoints
}

locals {
  vpc_id             = var.create_vpc ? module.network.vpc_id : var.existing_vpc_id
  public_subnet_ids  = var.create_vpc ? module.network.public_subnet_ids : var.existing_public_subnet_ids
  private_subnet_ids = var.create_vpc ? module.network.private_subnet_ids : var.existing_private_subnet_ids
}

resource "aws_security_group" "tasks" {
  name        = "${var.name_prefix}-tasks"
  description = "Staging ECS tasks; ingress is managed by the staging ECS module"
  vpc_id      = local.vpc_id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

module "storage" {
  source      = "../../modules/staging_storage"
  enabled     = var.enable_s3_storage
  bucket_name = var.artifact_bucket_name
  name_prefix = var.name_prefix
  cors_origin = var.enable_custom_domain && var.enable_https ? "https://${var.domain_name}" : ""
}

module "security" {
  source = "../../modules/staging_security"
  secret_names = toset(concat(
    ["database"],
    var.enable_cognito ? ["cognito"] : [],
    var.enable_stripe ? ["stripe"] : [],
    var.enable_ses ? ["email"] : [],
    var.enable_mock_ai ? [] : ["ai/openai", "ai/anthropic"],
  ))
}

module "database" {
  source                = "../../modules/staging_database"
  name_prefix           = var.name_prefix
  identifier            = var.rds_identifier
  vpc_id                = local.vpc_id
  subnet_ids            = var.create_vpc ? module.network.database_subnet_ids : local.private_subnet_ids
  application_sg_id     = aws_security_group.tasks.id
  instance_class        = var.db_instance_class
  multi_az              = var.db_multi_az
  backup_retention_days = var.backup_retention_days
  deletion_protection   = var.deletion_protection
}

module "ecs" {
  source                          = "../../modules/staging_ecs"
  name_prefix                     = var.name_prefix
  aws_region                      = var.aws_region
  vpc_id                          = local.vpc_id
  application_sg_id               = aws_security_group.tasks.id
  public_subnet_ids               = local.public_subnet_ids
  private_subnet_ids              = local.private_subnet_ids
  backend_image                   = var.backend_image_uri
  worker_image                    = var.worker_image_uri
  frontend_image                  = var.frontend_image_uri
  desired_count_backend           = var.desired_count_backend
  desired_count_worker            = var.desired_count_worker
  desired_count_frontend          = var.desired_count_frontend
  enable_runtime_services         = var.enable_runtime_services
  log_retention_days              = var.log_retention_days
  artifact_bucket_arn             = module.storage.bucket_arn
  application_database_secret_arn = module.security.database_secret_arn
  migration_database_secret_arn   = module.database.secret_arn
  application_secret_arns         = module.security.application_secret_arns
  enable_mock_ai                  = var.enable_mock_ai
  enable_mock_payment             = var.enable_mock_payment
  enable_mock_email               = var.enable_mock_email
  enable_cognito                  = var.enable_cognito
  enable_stripe                   = var.enable_stripe
  enable_ses                      = var.enable_ses
  enable_s3_storage               = var.enable_s3_storage
  stripe_mode                     = var.stripe_mode
  enable_https                    = var.enable_custom_domain && var.enable_https
  acm_certificate_arn             = local.effective_acm_certificate_arn
  cognito_user_pool_id            = var.cognito_user_pool_id
  cognito_app_client_id           = var.cognito_app_client_id
  cognito_issuer                  = var.cognito_issuer
  cognito_domain                  = var.cognito_domain
  stripe_publishable_key          = var.stripe_publishable_key
  stripe_webhook_endpoint         = var.stripe_webhook_endpoint
  ses_region                      = var.ses_region
  ses_from_address                = var.ses_from_address
  ses_configuration_set           = var.ses_configuration_set
  ses_sandbox_mode                = var.ses_sandbox_mode
}

module "monitoring" {
  source                        = "../../modules/staging_monitoring"
  name_prefix                   = var.name_prefix
  cluster_name                  = module.ecs.cluster_name
  backend_service_name          = module.ecs.backend_service_name
  worker_service_name           = module.ecs.worker_service_name
  frontend_service_name         = module.ecs.frontend_service_name
  alb_arn_suffix                = module.ecs.alb_arn_suffix
  target_group_arn_suffixes     = module.ecs.target_group_arn_suffixes
  db_identifier                 = module.database.identifier
  sns_topic_arn                 = var.prerequisite_sns_topic_arn
  desired_count_backend         = var.desired_count_backend
  desired_count_worker          = var.desired_count_worker
  rds_connections_threshold     = var.rds_connections_threshold
  rds_free_storage_threshold    = var.rds_free_storage_threshold
  rds_freeable_memory_threshold = var.rds_freeable_memory_threshold
  enable_runtime_services       = var.enable_runtime_services
}
