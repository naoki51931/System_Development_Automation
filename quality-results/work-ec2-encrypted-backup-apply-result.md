# Work EC2 encrypted backup apply result — 2026-08-12 UTC

The approved encrypted-backup and restore-test workflow completed successfully from clean Git HEAD `16016469d83129f32616656e1ab00fabb308e80a`. The execution identity was account `557604519341`, region `eu-west-2`, assumed role `instanceRoleTerraform`. No secret value was read, printed, or written.

## Snapshot result

The unencrypted 30 GiB source snapshot `snap-09251b0d48de70d17` is `completed` at `100%` and is retained. The earlier copy `snap-000caea04ca81bfef` remains an unused `FAILED_ENCRYPTED_COPY_ARTIFACT` with state `error` and message `Source snapshot is not complete`; it was neither reused nor deleted.

The replacement recovery snapshot `snap-0da911dd9bd13c867` is `completed`, encrypted, 30 GiB, and uses the enabled AWS-managed EBS key resolved from `alias/aws/ebs` (`arn:aws:kms:eu-west-2:557604519341:key/b444b2bf-73a7-41fa-90cd-e2c53098e3ed`). All three snapshots remain retained as required.

## Restore test and cleanup

Temporary encrypted gp3 volume `vol-045b7e4095e33d4af` was created in the work instance AZ `eu-west-2c` from the successful encrypted snapshot. It was attached as requested device `/dev/sdf` and unambiguously identified as `/dev/nvme1n1` by its EBS serial; the unchanged root remained `/dev/nvme0n1` / `vol-09baf3dfa613ea20d`.

The restored ext4 partition `/dev/nvme1n1p1` was mounted at `/mnt/work-ec2-restore-test` with effective options `ro,relatime,norecovery`. The repository and `.git` were readable. `scripts/verify_work_ec2_recovery.py` reported all six critical files present with 6/6 size matches and 6/6 SHA-256 matches: `WORK_EC2_RESTORE_TEST_PASS`.

Cleanup completed: the filesystem was unmounted, the volume was detached without force, it reached `available`, and it was deleted. A final describe returned `InvalidVolume.NotFound`.

## Final checks and decisions

The current root also matches the recovery manifest for all six files after cleanup. Work EC2 `i-0add395a2d89805b5` remains `running` with system and instance status `ok`, instance profile `instanceRoleTerraform`, and unchanged root EBS `vol-09baf3dfa613ea20d` as its only attached volume.

Production RDS was checked read-only. `ai-platform-prod-postgres` is `available`, current `db.t4g.medium`, pending `db.t4g.small`; the post-maintenance verifier was therefore not run. Decision: `RDS_DOWNSIZING_STILL_PENDING_MAINTENANCE`.

Final backup decisions:

- `WORK_EC2_ENCRYPTED_BACKUP_VALIDATED`
- `WORK_EC2_READY_FOR_SOURCE_SNAPSHOT_CLEANUP_APPROVAL`
- `WORK_EC2_READY_FOR_MANUAL_STOP_APPROVAL`
- `UNENCRYPTED_SOURCE_SNAPSHOT_CLEANUP_REQUIRED`

Source-snapshot cleanup and EC2 stop remain separate future human approvals. No snapshot was deleted and the EC2 was not stopped or started. No Terraform, RDS, ECS, NAT, Secret, database, migration, or GitHub mutation was performed.
