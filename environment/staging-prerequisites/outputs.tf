output "repository_urls" {
  value = module.ecr.repository_urls
}
output "repository_arns" {
  value = module.ecr.repository_arns
}
output "app_ecr_repository_url" { value = module.ecr.repository_urls["system-navigator-staging-app"] }
output "frontend_ecr_repository_url" { value = module.ecr.repository_urls["system-navigator-staging-frontend"] }
output "github_deploy_role_arn" { value = module.deploy_role.role_arn }
output "acm_certificate_arn" { value = try(module.dns[0].certificate_arn, null) }
output "sns_topic_arn" { value = module.notifications.sns_topic_arn }
output "alert_email_address" {
  value     = module.notifications.alert_email_address
  sensitive = true
}
output "budget_name" { value = module.notifications.budget_name }
