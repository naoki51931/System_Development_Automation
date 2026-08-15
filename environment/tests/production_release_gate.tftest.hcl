mock_provider "aws" {
  mock_data "aws_availability_zones" {
    defaults = { names = ["eu-west-2a", "eu-west-2b"] }
  }
}
mock_provider "random" {}

variables {
  aws_account_id       = "557604519341"
  aws_region           = "eu-west-2"
  name                 = "ai-platform-prod"
  artifact_bucket_name = "production-release-test-artifacts"
  github_org           = "naoki51931"
  github_repository    = "System_Development_Automation"
  approved_release_sha = "cccccccccccccccccccccccccccccccccccccccc"
  app_image_uri        = "557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  frontend_image_uri   = "557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod-frontend@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
}

run "runtime_disabled_preserves_backend" {
  command = plan
  variables { enable_release_runtime = false }
  assert {
    condition     = module.ecs.ecs_service_name == "ai-platform-prod"
    error_message = "The existing backend service must be preserved."
  }
}

run "valid_verified_handoff_passes" {
  command = plan
  variables { enable_release_runtime = true }
  assert {
    condition     = output.release_runtime_enabled == true
    error_message = "A valid verifier handoff must unlock the release topology."
  }
}

run "release_sha_mismatch_fails" {
  command = plan
  variables {
    enable_release_runtime = true
    approved_release_sha   = "dddddddddddddddddddddddddddddddddddddddd"
  }
  expect_failures = [check.migration_before_release_runtime, terraform_data.release_runtime_gate]
}

run "wrong_account_fails" {
  command = plan
  variables { aws_account_id = "000000000000" }
  expect_failures = [var.aws_account_id]
}

run "wrong_region_fails" {
  command = plan
  variables { aws_region = "us-east-1" }
  expect_failures = [var.aws_region]
}

run "wrong_repository_fails" {
  command = plan
  variables {
    app_image_uri = "557604519341.dkr.ecr.eu-west-2.amazonaws.com/wrong@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
  expect_failures = [var.app_image_uri]
}

run "tagged_or_unsigned_input_has_no_raw_interface" {
  command = plan
  variables {
    app_image_uri = "557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod:latest"
  }
  expect_failures = [var.app_image_uri]
}
