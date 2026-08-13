# Work EC2 manual-stop pre-execution evidence — 2026-08-13 UTC

Recorded before the authorized stop of `i-0add395a2d89805b5`. The post-stop AWS state is intentionally reported from the control terminal because this repository becomes unavailable when the instance stops.

## Final gate

All required identity, repository, recovery, process, storage, network, IAM, and stop-protection checks passed. AWS account `557604519341`, region `eu-west-2`, and assumed role `instanceRoleTerraform` match the approved target. The pre-evidence Git HEAD was `3b9b317bb63dfa0ae9f5d3860a1a1d4707b4cff1`, and the worktree was clean.

The retained source `snap-09251b0d48de70d17` is completed and unencrypted. The retained recovery snapshot `snap-06689648ebb6033aa` is completed at 100%, encrypted, 30 GiB, and uses the enabled AWS-managed EBS key. The earlier `snap-000caea04ca81bfef` remains the unused error artifact and must not be reused or deleted. The actual read-only restore test passed, and all six critical files again matched the recovery manifest by existence, size, and SHA-256 without exposing values.

Docker has zero running containers and local PostgreSQL is inactive. No Terraform, migration, build, test, local-database, or long-running AWS mutation process was found. The only Codex processes are this explicitly authorized control session. The root `vol-09baf3dfa613ea20d` is in-use, 30 GiB gp3, attached as `/dev/sda1`, and EBS-backed; normal stop preserves its attachment mapping. Stop protection is disabled. The instance has no Elastic IP; its pre-stop public IPv4 is `18.170.41.191`, private IPv4 is `172.31.0.175`, subnet is `subnet-09636511a5d33c952`, and AZ is `eu-west-2c`. Its instance profile is `instanceRoleTerraform`.

Production RDS `ai-platform-prod-postgres` is available on `db.t4g.medium` with `db.t4g.small` pending maintenance. No post-maintenance verifier was run and no Production change was made. Decision: `RDS_DOWNSIZING_STILL_PENDING_MAINTENANCE`.

Decisions: `STOP_COMMAND_AUTHORIZED`, `STOP_EXECUTION_PENDING`, `WORK_EC2_READY_FOR_MANUAL_STOP`.

Only one future AWS mutation is authorized by this evidence: one `stop-instances` call for `i-0add395a2d89805b5`. Termination, detach/delete, snapshot mutation, start, Terraform, Production/Staging mutation, Secret/DB/migration, and GitHub push remain prohibited.
