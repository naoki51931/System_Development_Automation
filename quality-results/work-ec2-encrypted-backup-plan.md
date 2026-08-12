# Work EC2 encrypted backup plan review — 2026-08-12 UTC

No AWS resource was changed. Start Gate passed at clean HEAD `d8a5246ef081787044857c9c03e464bd86f70ef3`, account `557604519341`, region `eu-west-2`, assumed role `instanceRoleTerraform`.

## Inventory and recovery scope

`i-0add395a2d89805b5` is a running `t3.medium`. Its EBS root is `vol-09baf3dfa613ea20d`, `in-use`, 30 GiB gp3, 3000 IOPS/125 MiB/s, unencrypted (`KmsKeyId=null`), in `eu-west-2c`, attached as `/dev/sda1`, and `DeleteOnTermination=true`. The volume's original AMI source is public Canonical snapshot `snap-0e7a248875fcfb2cf` (8 GiB, unencrypted); it is not a current owner backup. Owner snapshots for this volume are zero. Termination/stop protection are disabled. The root is EBS-backed and `t3.medium` has no instance store.

Recovery classes:

- `MUST_RECOVER`: the repository including Git metadata; six ignored Production/Staging/staging-prerequisites backend/tfvars files covered by `work-ec2-recovery-manifest.json`; user SSH/AWS/Git configuration metadata required for access; selected local evidence not already pushed; and any explicitly retained Docker PostgreSQL test data.
- `REGENERABLE`: tracked repository content from origin, Terraform provider/work caches, node modules/build output, Playwright/npm/pip/Ruff/pytest caches, Docker images/build cache, and current-state Terraform plans generated after a fresh init/plan.
- `STALE_INVALID`: every saved plan already applied or partially applied and its review text; never use it as recovery input or reapply it.
- `OPTIONAL`: exited containers, local test databases/artifacts not designated for retention, coverage/log output, and other developer caches.

The six secret-bearing files are ignored and not tracked. Their contents were not read or logged; manifest hashes remain the integrity source.

## Options and KMS review

Option A, normal snapshot, is insufficient as the retained backup. AWS states a snapshot inherits its source volume's encryption status, so this unencrypted volume produces an unencrypted snapshot. A volume restored from it is also unencrypted by default because EBS encryption by default is disabled in this account/region, unless encryption is explicitly requested.

Option B, unencrypted source snapshot followed by encrypted copy, is selected. AWS supports encrypting an unencrypted snapshot during `copy-snapshot`; changing encryption/key makes a full copy. The source is retained only until copy and restore verification succeed, then deletion requires separate approval.

Option C, encrypted AMI/replacement root, protects a broader bootable artifact or permanently migrates the instance, but adds image/block mappings or instance/volume replacement risk. It is excessive for pre-stop protection and belongs in a separate root-volume encryption project.

KMS selection is the AWS-managed `alias/aws/ebs`: EBS default encryption is currently disabled but the configured default key alias is `alias/aws/ebs`; its backing key will be created lazily on first use. It has no customer-managed key monthly fee, minimizes policy/lifecycle risk, and cross-account recovery is not required. The enabled customer-managed key found is described as Terraform state encryption; reusing it would couple unrelated lifecycles. A dedicated customer-managed key would offer policy control and cross-account sharing but adds roughly `$1/month`, IAM/key deletion/disable risks, and is prohibited in this task.

Decision: **RECOMMEND_ENCRYPTED_SNAPSHOT_COPY**.

## Consistency, restore and cleanup

AWS recommends stopping an EBS-root instance for the strongest snapshot consistency. Because backup must precede stop approval, the approved compromise is application/filesystem quiescence: finish and commit work, stop local Docker/PostgreSQL and all builds/tests/Terraform/Codex writers, run `sync`, verify no critical process, then create the snapshot. Do not `fsfreeze` the live root from the same session because it can deadlock control and recovery. The resulting snapshot is crash-consistent rather than a substitute for application-native database backup; local PostgreSQL is test data and no database connection/migration is authorized. Restore/hash testing is mandatory.

Level 1 verifies encrypted snapshot `completed`, `Encrypted=true`, 30 GiB, source/copy descriptions and resolved KMS key. Level 2 creates a temporary encrypted 30 GiB gp3 volume in `eu-west-2c`, attaches it to the current work instance as a secondary device, mounts the ext4 filesystem read-only with journal replay disabled, and uses `verify_work_ec2_recovery.py`. Success requires filesystem mount, readable Git repository, all six critical files present with matching size/hash, and expected Docker/config paths—never secret content output. A separate test instance is optional, not required; if used, it needs isolated networking, no public IP, a compatible AMI, then explicit termination cleanup.

Cleanup order: unmount, detach, wait available, delete temporary volume, verify deletion; remove any temporary instance/ENI/security group; retain encrypted snapshot; only then seek separate approval to delete the unencrypted source. Orphaned volumes/instances/snapshots continue billing.

## Disk cleanup and cost

Root remains 91% used (2.7 GiB free). No deletion occurred. Separately approved candidates are Docker build cache 2.807 GiB and unused images; Playwright cache 1.2 GiB; Terraform caches about 3.4 GiB across four roots; frontend node modules 626 MiB and `.next` 28 MiB; npm cache 254 MiB; Ruff/pytest/coverage/log data below 1 MiB. Docker PostgreSQL volumes total about 453 MiB and need owner confirmation before cleanup.

Snapshot Standard storage is billed for stored changed blocks, not provisioned capacity. A conservative full 30 GiB estimate at `$0.05/GB-month` is `$1.50/month`; while both source and encrypted full copy exist, maximum storage is about `$3/month`, prorated. The temporary restore gp3 volume is `$2.784/month` or about `$0.0038/hour`; a two-hour test is under `$0.01`. Attaching to the current instance avoids temporary EC2 compute; an optional two-hour `t3.micro`-class test is only a few cents plus public IPv4 if used.

Against maximum stop savings `$38.11/month`, retaining one conservative full encrypted snapshot yields net savings about **`$36.61/month`**. Combined maximum Staging + Production + net work-EC2 saving becomes approximately **`$298.61–301.61/month`**.

## Approval Gate

Before stop: `ENCRYPTED_RECOVERY_SNAPSHOT_AVAILABLE`, `ENCRYPTED_RECOVERY_SNAPSHOT_KMS_VALID`, `RESTORE_TEST_PASSED` or explicit human waiver, manifest hashes match, clean worktree, no critical process, EBS persistence confirmed, public-IP change documented, and IAM role recovery defined. Only then may the separate stop decision become `WORK_EC2_READY_FOR_MANUAL_STOP_APPROVAL`.

Current backup decision: **READY_FOR_WORK_EC2_ENCRYPTED_BACKUP_APPLY_APPROVAL**. This is approval readiness for the reviewed backup/copy/restore workflow only; EC2 stop is not approved.

Related tests passed: 36. Ruff check/format, Bandit, compileall, pip-audit (0 known vulnerabilities), JSON validation, and the repository secret scan passed. The quality image retains pip `26.1.2`; restore-check output contains file status/hash comparison only, never file content.

Production RDS remains `available`, current `db.t4g.medium`, pending `db.t4g.small`, Multi-AZ; therefore `RDS_DOWNSIZING_STILL_PENDING_MAINTENANCE` remains unchanged and the post-maintenance verifier was not run.
