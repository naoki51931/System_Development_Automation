variable "name_prefix" { type = string }
variable "aws_account_id" { type = string }
variable "aws_region" { type = string }
variable "github_oidc_provider_arn" { type = string }
variable "github_org" { type = string }
variable "github_repository" { type = string }
variable "github_environment" { type = string }
variable "ecr_repository_arns" { type = list(string) }
variable "state_bucket_name" { type = string }
variable "state_kms_key_arn" { type = string }

data "aws_iam_policy_document" "trust" {
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
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repository}:environment:${var.github_environment}"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name               = "${var.name_prefix}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.trust.json
}

data "aws_iam_policy_document" "deploy" {
  # AWS does not support resource-level scoping for these two API actions.
  statement {
    sid       = "UnscopableEcrLoginAndTaskRegistration"
    actions   = ["ecr:GetAuthorizationToken", "ecs:RegisterTaskDefinition"]
    resources = ["*"]
  }
  statement {
    sid       = "PushReviewedStagingImages"
    actions   = ["ecr:BatchCheckLayerAvailability", "ecr:CompleteLayerUpload", "ecr:GetDownloadUrlForLayer", "ecr:InitiateLayerUpload", "ecr:PutImage", "ecr:UploadLayerPart"]
    resources = var.ecr_repository_arns
  }
  statement {
    sid       = "StagingTaskDefinitionsOnly"
    actions   = ["ecs:DescribeTaskDefinition"]
    resources = ["arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.name_prefix}-*"]
  }
  statement {
    sid     = "StagingServicesOnly"
    actions = ["ecs:DescribeServices", "ecs:UpdateService", "ecs:RunTask"]
    resources = [
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:service/${var.name_prefix}-cluster/${var.name_prefix}-*",
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.name_prefix}-*",
    ]
  }
  statement {
    sid       = "PassStagingRolesOnly"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${var.aws_account_id}:role/${var.name_prefix}-*"]
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

resource "aws_iam_role_policy" "deploy" {
  name   = "staging-deploy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}

output "role_arn" { value = aws_iam_role.deploy.arn }
