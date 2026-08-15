terraform { required_version = ">= 1.7.0" }

# TEST FIXTURE ONLY. Production never loads this module or these values.
variable "enable_release_runtime" {
  type    = bool
  default = true
}
variable "handoff_present" {
  type    = bool
  default = true
}
variable "release_sha" {
  type    = string
  default = "cccccccccccccccccccccccccccccccccccccccc"
}
variable "signing_key_id" {
  type    = string
  default = "production-release-2026-01"
}
variable "artifact_signature" {
  type    = string
  default = "dGVzdC1vbmx5LXZhbGlkLXNpZ25hdHVyZQ=="
}
variable "exit_code" {
  type    = number
  default = 0
}
variable "verified_alembic_head" {
  type    = string
  default = "8d4f2a7c9b11"
}
variable "verified_at" {
  type    = string
  default = "2026-08-15T00:00:00Z"
}
variable "handoff_verified_at" {
  type    = string
  default = "2026-08-15T00:01:00Z"
}
variable "aws_account_id" {
  type    = string
  default = "557604519341"
}
variable "aws_region" {
  type    = string
  default = "eu-west-2"
}
variable "github_repository" {
  type    = string
  default = "naoki51931/System_Development_Automation"
}
variable "verifier_receipt_sha256" {
  type    = string
  default = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
}

locals {
  fixture_valid = var.handoff_present && (
    var.release_sha == "cccccccccccccccccccccccccccccccccccccccc" &&
    var.signing_key_id == "production-release-2026-01" &&
    var.artifact_signature == "dGVzdC1vbmx5LXZhbGlkLXNpZ25hdHVyZQ==" &&
    var.verifier_receipt_sha256 == "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee" &&
    var.exit_code == 0 &&
    var.verified_alembic_head == "8d4f2a7c9b11" &&
    var.aws_account_id == "557604519341" &&
    var.aws_region == "eu-west-2" &&
    var.github_repository == "naoki51931/System_Development_Automation" &&
    can(timecmp(var.verified_at, "2026-08-15T00:00:00Z")) &&
    timecmp(var.verified_at, "2026-08-14T00:00:00Z") >= 0 &&
    timecmp(var.verified_at, "2026-08-15T01:05:00Z") <= 0 &&
    can(timecmp(var.handoff_verified_at, "2026-08-15T00:00:00Z")) &&
    timecmp(var.handoff_verified_at, "2026-08-14T00:00:00Z") >= 0 &&
    timecmp(var.handoff_verified_at, "2026-08-15T01:05:00Z") <= 0
  )
}

resource "terraform_data" "release_gate" {
  lifecycle {
    precondition {
      condition     = !var.enable_release_runtime || local.fixture_valid
      error_message = "MIGRATION_SEQUENCE_UNSAFE"
    }
  }
}
