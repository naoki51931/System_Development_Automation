mock_provider "aws" {
  mock_data "aws_availability_zones" {
    defaults = {
      names = ["eu-west-2a", "eu-west-2b"]
    }
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
  variables {
    enable_release_runtime = false
    migration_attestation  = null
  }
  assert {
    condition     = module.ecs.ecs_service_name == "ai-platform-prod"
    error_message = "The existing backend service address/name must remain active."
  }
  assert {
    condition     = output.release_runtime_enabled == false
    error_message = "The disabled gate must not select the digest runtime rollout."
  }
}

run "runtime_missing_attestation_hard_fails" {
  command = plan
  variables {
    enable_release_runtime = true
    migration_attestation  = null
  }
  expect_failures = [
    check.migration_before_release_runtime,
    terraform_data.release_runtime_gate,
  ]
}

run "runtime_digest_mismatch_hard_fails" {
  command = plan
  variables {
    enable_release_runtime = true
    migration_attestation = {
      schema_version                     = 1
      release_sha                        = "cccccccccccccccccccccccccccccccccccccccc"
      aws_account_id                     = "557604519341"
      aws_region                         = "eu-west-2"
      ecs_cluster_arn                    = "arn:aws:ecs:eu-west-2:557604519341:cluster/ai-platform-prod"
      migration_task_arn                 = "arn:aws:ecs:eu-west-2:557604519341:task/ai-platform-prod/1234567890abcdef1234567890abcdef"
      migration_task_definition_arn      = "arn:aws:ecs:eu-west-2:557604519341:task-definition/ai-platform-prod-migration:7"
      migration_task_definition_revision = 7
      app_image_uri                      = "557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod@sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
      resolved_image_digest              = "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
      container_name                     = "migration"
      exit_code                          = 0
      stopped_reason                     = "Essential container in task exited"
      expected_alembic_head              = "8d4f2a7c9b11"
      verified_alembic_head              = "8d4f2a7c9b11"
      alembic_verification_method        = "approved migration verification task"
      alembic_verification_reference     = "run-123"
      verified_at                        = "2026-08-14T00:00:00+00:00"
      github_repository                  = "naoki51931/System_Development_Automation"
      github_workflow                    = "production-release"
      github_run_id                      = 123
      github_run_attempt                 = 1
      github_job                         = "migration-attestation"
      github_sha                         = "cccccccccccccccccccccccccccccccccccccccc"
      github_ref                         = "refs/heads/master"
      signature_algorithm                = "Ed25519"
      signing_key_id                     = "prod-release-1"
      artifact_sha256                    = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
      artifact_signature                 = "signed-payload"
    }
  }
  expect_failures = [
    check.migration_before_release_runtime,
    terraform_data.release_runtime_gate,
  ]
}

run "verified_runtime_gate_passes" {
  command = plan
  variables {
    enable_release_runtime = true
    migration_attestation = {
      schema_version                     = 1
      release_sha                        = "cccccccccccccccccccccccccccccccccccccccc"
      aws_account_id                     = "557604519341"
      aws_region                         = "eu-west-2"
      ecs_cluster_arn                    = "arn:aws:ecs:eu-west-2:557604519341:cluster/ai-platform-prod"
      migration_task_arn                 = "arn:aws:ecs:eu-west-2:557604519341:task/ai-platform-prod/1234567890abcdef1234567890abcdef"
      migration_task_definition_arn      = "arn:aws:ecs:eu-west-2:557604519341:task-definition/ai-platform-prod-migration:7"
      migration_task_definition_revision = 7
      app_image_uri                      = "557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      resolved_image_digest              = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      container_name                     = "migration"
      exit_code                          = 0
      stopped_reason                     = "Essential container in task exited"
      expected_alembic_head              = "8d4f2a7c9b11"
      verified_alembic_head              = "8d4f2a7c9b11"
      alembic_verification_method        = "approved migration verification task"
      alembic_verification_reference     = "run-123"
      verified_at                        = "2026-08-14T00:00:00+00:00"
      github_repository                  = "naoki51931/System_Development_Automation"
      github_workflow                    = "production-release"
      github_run_id                      = 123
      github_run_attempt                 = 1
      github_job                         = "migration-attestation"
      github_sha                         = "cccccccccccccccccccccccccccccccccccccccc"
      github_ref                         = "refs/heads/master"
      signature_algorithm                = "Ed25519"
      signing_key_id                     = "prod-release-1"
      artifact_sha256                    = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
      artifact_signature                 = "signed-payload"
    }
  }
  assert {
    condition = (
      output.release_runtime_enabled == true &&
      module.ecs.frontend_service_name == "ai-platform-prod-frontend" &&
      module.ecs.worker_service_name == "ai-platform-prod-worker" &&
      length(output.release_task_definition_arns) == 4
    )
    error_message = "The verified gate must expose backend/frontend/worker/migration release topology."
  }
}

run "wrong_account_fails" {
  command = plan
  variables { aws_account_id = "000000000000" }
  expect_failures = [var.aws_account_id]
}

run "approved_release_sha_mismatch_fails" {
  command = plan
  variables {
    approved_release_sha = "dddddddddddddddddddddddddddddddddddddddd"
  }
  expect_failures = [terraform_data.release_runtime_gate]
}

run "wrong_region_fails" {
  command = plan
  variables { aws_region = "us-east-1" }
  expect_failures = [var.aws_region]
}

run "wrong_app_repository_fails" {
  command = plan
  variables {
    app_image_uri = "557604519341.dkr.ecr.eu-west-2.amazonaws.com/wrong@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
  expect_failures = [var.app_image_uri]
}

run "tagged_app_image_fails" {
  command = plan
  variables {
    app_image_uri = "557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod:latest"
  }
  expect_failures = [var.app_image_uri]
}

run "short_digest_fails" {
  command = plan
  variables {
    app_image_uri = "557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod@sha256:abc"
  }
  expect_failures = [var.app_image_uri]
}

run "uppercase_digest_fails" {
  command = plan
  variables {
    app_image_uri = "557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod@sha256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
  }
  expect_failures = [var.app_image_uri]
}
