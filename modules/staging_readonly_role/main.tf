variable "role_name" {
  type    = string
  default = "system-navigator-staging-readonly"

  validation {
    condition     = var.role_name == "system-navigator-staging-readonly"
    error_message = "The verification role name is fixed to the staging read-only role."
  }
}

variable "aws_account_id" {
  type = string

  validation {
    condition     = var.aws_account_id == "557604519341"
    error_message = "This role is restricted to AWS account 557604519341."
  }
}

variable "aws_region" {
  type = string

  validation {
    condition     = var.aws_region == "eu-west-2"
    error_message = "This role is restricted to eu-west-2."
  }
}

variable "github_oidc_provider_arn" { type = string }

variable "github_org" {
  type    = string
  default = "naoki51931"
}

variable "github_repository" {
  type    = string
  default = "System_Development_Automation"
}

variable "github_environment" {
  type    = string
  default = "staging-readonly"

  validation {
    condition     = var.github_environment == "staging-readonly"
    error_message = "The trust policy must use the staging-readonly GitHub Environment."
  }
}

variable "state_bucket_name" {
  type    = string
  default = "ai-platform-terraform-state-557604519341"

  validation {
    condition     = var.state_bucket_name == "ai-platform-terraform-state-557604519341"
    error_message = "The read-only role may inspect only the approved staging state bucket."
  }
}

data "aws_iam_policy_document" "trust" {
  statement {
    sid     = "GitHubActionsStagingReadonlyOnly"
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

resource "aws_iam_role" "staging_readonly" {
  name               = var.role_name
  assume_role_policy = data.aws_iam_policy_document.trust.json
}

data "aws_iam_policy_document" "staging_readonly" {
  statement {
    sid = "ReadOnlyStagingInventory"
    actions = [
      "acm:DescribeCertificate",
      "acm:ListCertificates",
      "ecs:DescribeClusters",
      "ecs:DescribeServices",
      "ecs:DescribeTasks",
      "ecs:ListClusters",
      "ecs:ListServices",
      "ecs:ListTasks",
      "rds:DescribeDBInstances",
      "rds:DescribeDBSnapshots",
      "elasticloadbalancing:DescribeLoadBalancers",
      "elasticloadbalancing:DescribeTargetGroups",
      "elasticloadbalancing:DescribeListeners",
      "ecr:DescribeRepositories",
      "ecr:DescribeImages",
      "ecr:ListImages",
      "ec2:DescribeVpcs",
      "ec2:DescribeSubnets",
      "ec2:DescribeRouteTables",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeVpcEndpoints",
      "ec2:DescribeNatGateways",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "ListStagingStateKeyOnly"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.state_bucket_name}"]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["system-navigator/staging/*"]
    }
  }
}

resource "aws_iam_role_policy" "staging_readonly" {
  name   = "staging-readonly-inventory"
  role   = aws_iam_role.staging_readonly.id
  policy = data.aws_iam_policy_document.staging_readonly.json
}

output "staging_readonly_role_arn" {
  value = aws_iam_role.staging_readonly.arn
}
