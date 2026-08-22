output "alb_dns_name" { value = module.ecs.alb_dns_name }
output "ecr_repository_url" { value = module.ecs.ecr_repository_url }
output "frontend_ecr_repository_url" { value = module.ecs.frontend_ecr_repository_url }
output "release_task_definition_arns" { value = module.ecs.release_task_definition_arns }
output "release_runtime_enabled" { value = module.ecs.release_runtime_enabled }
output "external_launch_ready" { value = false }
output "artifact_bucket_name" { value = module.storage.bucket_name }
output "database_secret_arn" {
  value     = module.database.secret_arn
  sensitive = true
}
output "github_deploy_role_arn" { value = aws_iam_role.github_deploy.arn }
