mock_provider "aws" {
  mock_data "aws_availability_zones" {
    defaults = { names = ["eu-west-2a", "eu-west-2b"] }
  }
}
mock_provider "random" {}

variables {
  artifact_bucket_name = "production-release-test-artifacts"
  github_org           = "naoki51931"
  github_repository    = "System_Development_Automation"
  approved_release_sha = "cccccccccccccccccccccccccccccccccccccccc"
  app_image_uri        = "557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  frontend_image_uri   = "557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod-frontend@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  enable_release_runtime = true
}

run "missing_verifier_handoff_hard_fails" {
  command = plan
  expect_failures = [check.migration_before_release_runtime, terraform_data.release_runtime_gate]
}
