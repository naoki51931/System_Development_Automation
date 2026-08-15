run "valid_verified_handoff_passes" { command = plan }

run "runtime_disabled_preserves_backend_contract" {
  command = plan
  variables {
    enable_release_runtime = false
    handoff_present        = false
  }
}

run "missing_handoff_fails" {
  command = plan
  variables {
    handoff_present = false
  }
  expect_failures = [terraform_data.release_gate]
}

run "fake_signature_fails" {
  command = plan
  variables {
    artifact_signature = "TEST-ONLY-NOT-A-REAL-SIGNATURE"
  }
  expect_failures = [terraform_data.release_gate]
}

run "unsigned_fails" {
  command = plan
  variables {
    artifact_signature = ""
  }
  expect_failures = [terraform_data.release_gate]
}

run "wrong_key_fails" {
  command = plan
  variables {
    signing_key_id = "attacker-key"
  }
  expect_failures = [terraform_data.release_gate]
}

run "exit_non_zero_fails" {
  command = plan
  variables {
    exit_code = 1
  }
  expect_failures = [terraform_data.release_gate]
}

run "alembic_mismatch_fails" {
  command = plan
  variables {
    verified_alembic_head = "wrong"
  }
  expect_failures = [terraform_data.release_gate]
}

run "stale_fails" {
  command = plan
  variables {
    verified_at = "2026-08-13T00:00:00Z"
  }
  expect_failures = [terraform_data.release_gate]
}

run "future_fails" {
  command = plan
  variables {
    verified_at = "2026-08-15T01:06:00Z"
  }
  expect_failures = [terraform_data.release_gate]
}
