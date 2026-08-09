output "state_key" {
  value = "system-navigator/staging/terraform.tfstate"
}
output "vpc_id" {
  value = local.vpc_id
}
output "alb_dns_name" {
  value = module.ecs.alb_dns_name
}
output "staging_url" {
  value = var.enable_custom_domain && var.enable_https ? "https://${var.domain_name}" : "http://${module.ecs.alb_dns_name}"
}
output "acm_certificate_arn" {
  value = local.effective_acm_certificate_arn
}
output "ecs_cluster_name" {
  value = module.ecs.cluster_name
}
output "backend_service_name" {
  value = module.ecs.backend_service_name
}
output "worker_service_name" {
  value = module.ecs.worker_service_name
}
output "frontend_service_name" {
  value = module.ecs.frontend_service_name
}
output "migration_task_definition_arn" {
  value = module.ecs.migration_task_definition_arn
}
output "artifact_bucket_name" {
  value = module.storage.bucket_name
}
output "database_identifier" {
  value = module.database.identifier
}
output "application_database_secret_arn" {
  value     = module.security.database_secret_arn
  sensitive = true
}
output "rds_master_secret_arn" {
  value     = module.database.secret_arn
  sensitive = true
}
output "github_staging_deploy_role_arn" {
  value = var.prerequisite_github_deploy_role_arn
}
