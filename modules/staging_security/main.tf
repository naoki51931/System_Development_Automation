variable "secret_names" {
  type = set(string)
  validation {
    condition     = contains(var.secret_names, "database")
    error_message = "The staging database Secret container is always required."
  }
}

# Containers only. Secret values are populated by a separately approved procedure.
resource "aws_secretsmanager_secret" "application" {
  for_each                = var.secret_names
  name                    = "/system-navigator/staging/${each.key}"
  recovery_window_in_days = 30
}

output "application_secret_arns" { value = values(aws_secretsmanager_secret.application)[*].arn }
output "database_secret_arn" {
  value     = aws_secretsmanager_secret.application["database"].arn
  sensitive = true
}
