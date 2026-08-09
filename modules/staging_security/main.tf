variable "name_prefix" { type = string }
variable "github_oidc_provider_arn" { type = string }
variable "github_org" { type = string }
variable "github_repository" { type = string }
variable "aws_account_id" { type = string }
variable "aws_region" { type = string }
variable "staging_app_repository_name" { type = string }
variable "staging_frontend_repository_name" { type = string }
variable "state_bucket_name" { type = string }
variable "state_kms_key_arn" { type = string }
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
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid = "PushReviewedStagingImages"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [
      "arn:aws:ecr:${var.aws_region}:${var.aws_account_id}:repository/${var.staging_app_repository_name}",
      "arn:aws:ecr:${var.aws_region}:${var.aws_account_id}:repository/${var.staging_frontend_repository_name}",
    ]
  }
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
  statement {
    sid       = "ReadStagingLogs"
    actions   = ["logs:DescribeLogStreams", "logs:GetLogEvents", "logs:FilterLogEvents"]
    resources = ["arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/system-navigator/staging/*"]
  }
  statement {
    sid       = "ListStagingState"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.state_bucket_name}"]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["system-navigator/staging/*"]
    }
  }
  statement {
    sid       = "UseStagingStateObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${var.state_bucket_name}/system-navigator/staging/*"]
  }
  statement {
    sid       = "UseStagingStateKey"
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
    resources = [var.state_kms_key_arn]
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
