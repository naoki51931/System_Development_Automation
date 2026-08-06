variable "name_prefix" { type = string }
variable "github_oidc_provider_arn" { type = string }
variable "github_org" { type = string }
variable "github_repository" { type = string }

locals {
  secret_names = toset([
    "database",
    "cognito",
    "stripe",
    "email",
    "ai/openai",
    "ai/anthropic",
  ])
}

# Containers only. Secret values are populated by a separately approved procedure.
resource "aws_secretsmanager_secret" "application" {
  for_each                = local.secret_names
  name                    = "/system-navigator/staging/${each.key}"
  recovery_window_in_days = 30
}

data "aws_iam_policy_document" "github_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.github_oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repository}:environment:staging"]
    }
  }
}

resource "aws_iam_role" "github_staging_deploy" {
  name               = "${var.name_prefix}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_trust.json
}

data "aws_iam_policy_document" "github_staging_deploy" {
  statement {
    sid       = "RegisterTaskDefinitions"
    actions   = ["ecs:RegisterTaskDefinition", "ecs:DescribeTaskDefinition"]
    resources = ["*"]
  }
  statement {
    sid       = "StagingServicesOnly"
    actions   = ["ecs:DescribeServices", "ecs:UpdateService", "ecs:RunTask"]
    resources = ["arn:aws:ecs:*:*:service/${var.name_prefix}/*", "arn:aws:ecs:*:*:task-definition/${var.name_prefix}-*"]
  }
  statement {
    sid       = "PassStagingRolesOnly"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::*:role/${var.name_prefix}-*"]
  }
}
resource "aws_iam_role_policy" "github_staging_deploy" {
  name   = "staging-deploy"
  role   = aws_iam_role.github_staging_deploy.id
  policy = data.aws_iam_policy_document.github_staging_deploy.json
}

output "application_secret_arns" { value = values(aws_secretsmanager_secret.application)[*].arn }
output "database_secret_arn" {
  value     = aws_secretsmanager_secret.application["database"].arn
  sensitive = true
}
output "github_staging_deploy_role_arn" { value = aws_iam_role.github_staging_deploy.arn }
