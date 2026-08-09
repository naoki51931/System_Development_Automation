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
