variable "aws_account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain 12 digits."
  }
}
variable "aws_region" {
  type    = string
  default = "eu-west-2"
}
variable "container_image_tag" {
  type    = string
  default = "57109fa"
  validation {
    condition     = can(regex("^[0-9a-f]{7,40}$", var.container_image_tag)) && var.container_image_tag != "latest"
    error_message = "Use a Git commit SHA; latest is forbidden."
  }
}
variable "repository_names" {
  type = set(string)
  default = [
    "system-navigator-staging-app",
    "system-navigator-staging-frontend",
  ]
}
variable "retain_tagged_images" {
  type    = number
  default = 20
}
variable "environment" {
  type    = string
  default = "staging"
  validation {
    condition     = var.environment == "staging"
    error_message = "This root is staging-only."
  }
}
variable "name_prefix" {
  type    = string
  default = "system-navigator-staging"
  validation {
    condition     = var.name_prefix == "system-navigator-staging"
    error_message = "The prerequisite prefix must remain staging-specific."
  }
}
variable "github_oidc_provider_arn" { type = string }
variable "github_org" { type = string }
variable "github_repository" { type = string }
variable "github_environment" {
  type    = string
  default = "staging"
  validation {
    condition     = var.github_environment == "staging"
    error_message = "GitHub trust must use the staging Environment."
  }
}
variable "github_readonly_environment" {
  type    = string
  default = "staging-readonly"
  validation {
    condition     = var.github_readonly_environment == "staging-readonly"
    error_message = "The verification role must use the staging-readonly Environment."
  }
}
variable "state_bucket_name" { type = string }
variable "state_kms_key_arn" { type = string }
variable "enable_custom_domain" {
  type        = bool
  description = "Create the approved staging ACM certificate independently of idle runtime."
  default     = true
}
variable "domain_name" {
  type    = string
  default = "test.system-navigation.com"
  validation {
    condition     = !var.enable_custom_domain || var.domain_name == "test.system-navigation.com"
    error_message = "The approved staging domain is test.system-navigation.com."
  }
}
variable "dns_provider" {
  type        = string
  description = "Authoritative DNS integration. external outputs manual records; route53 manages them."
  default     = "external"
  validation {
    condition     = contains(["external", "route53"], var.dns_provider)
    error_message = "dns_provider must be external or route53."
  }
}
variable "route53_zone_id" {
  type    = string
  default = ""
  validation {
    condition     = !var.enable_custom_domain || var.dns_provider == "external" || trimspace(var.route53_zone_id) != ""
    error_message = "Route53 mode requires a hosted zone ID; external DNS does not."
  }
}
variable "alarm_notification_email" {
  type      = string
  sensitive = true
  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alarm_notification_email))
    error_message = "A valid staging notification email is required."
  }
}
variable "monthly_budget_amount" {
  type    = number
  default = 150
  validation {
    condition     = var.monthly_budget_amount == 150
    error_message = "The approved staging Budget is 150 USD."
  }
}
variable "enable_budget" {
  type        = bool
  description = "Create the staging Budget only after its separate human approval."
  default     = false
}
variable "budget_currency" {
  type    = string
  default = "USD"
  validation {
    condition     = var.budget_currency == "USD"
    error_message = "This AWS account supports only USD for the staging Budget."
  }
}
