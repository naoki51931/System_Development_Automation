output "alb_dns_name" { value = module.ecs.alb_dns_name }
output "ecr_repository_url" { value = module.ecs.ecr_repository_url }
output "artifact_bucket_name" { value = module.storage.bucket_name }
output "database_secret_arn" {
  value     = module.database.secret_arn
  sensitive = true
}
output "github_deploy_role_arn" { value = aws_iam_role.github_deploy.arn }
