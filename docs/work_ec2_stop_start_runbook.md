# Work EC2 stop/start runbook

Scope: `i-0add395a2d89805b5` in `eu-west-2`. This instance is an operator workstation, not a Production Terraform resource. Stop or start requires explicit human approval. The commands below are examples and were not run while preparing this document.

## Current persistence and access model

- The instance is `t3.medium` and has no instance store. `/home/ubuntu`, the repository, Docker root (`/var/lib/docker`), and Docker volumes are on the 30 GiB gp3 root EBS volume `vol-09baf3dfa613ea20d`.
- EBS persists across stop/start. `/tmp` is tmpfs and does not persist.
- The volume is unencrypted and has `DeleteOnTermination=true`. Stop does not delete it, but termination would. Validated recovery snapshot `snap-0da911dd9bd13c867` is encrypted with the AWS-managed EBS key; source snapshot `snap-09251b0d48de70d17` remains pending separately approved cleanup.
- The current public IPv4 is auto-assigned; there is no Elastic IP. Stop/start normally releases it and assigns a different address. Private IPv4 normally remains attached to the primary network interface.
- AWS credentials come from IMDSv2 and `instanceRoleTerraform`. Do not copy temporary credentials to disk.

The recovery manifest is `quality-results/work-ec2-recovery-manifest.json`. It stores only path, size, modification time, SHA-256, and classification; it does not store file contents.

## Stop gate

All items must pass immediately before an approved stop:

1. Confirm the exact instance, account, region, and role:

   ```bash
   aws sts get-caller-identity
   aws configure get region
   aws ec2 describe-instances --instance-ids i-0add395a2d89805b5 --region eu-west-2
   ```

2. Confirm every repository is clean. Commit allowed code/docs or preserve unfinished work by an explicitly approved secure method. Never commit credentials, tfvars, backend configuration, state, or saved plans.

   ```bash
   cd /home/ubuntu/ai-platform
   git status --short
   git rev-parse HEAD
   ```

3. Validate the recovery manifest without printing file contents:

   ```bash
   python3 scripts/check_work_ec2_stop_readiness.py
   ```

   It must report matching hashes for all six critical files. A changed hash requires intentional manifest review and commit; never update a hash merely to silence a mismatch.
4. Inventory without printing contents: `environment/{backend.hcl,terraform.tfvars}`, equivalent Staging and staging-prerequisites files, saved plans/reviews, and local evidence. Treat tfvars/backend files as secret-bearing and must-preserve. Treat convergence plans as regenerable; treat already applied/partially applied plans as stale and never reapply them.
5. Verify an approved secure backup/recovery path for must-preserve local-only files. The current root EBS has no snapshot; do not stop on the assumption that Git contains ignored configuration. Set `external_backup_verified` only after a human has verified the approved backup and restore procedure.
6. Confirm no Terraform apply/plan, Docker build/compose, migration, database test/server, pytest, Playwright/browser test, npm build, deployment, Production operational process, or SSH-dependent long job is running. `docker ps` must show no workload that must remain available.
7. Confirm the filesystem is EBS-backed, mounts are healthy, disk use is below the 95% fail-closed threshold, and no required data exists only under `/tmp`.
8. Record the current public/private IPs and update the access plan. Document any SSH allowlist, DNS record, or external integration tied to the public IPv4.
9. End the active Codex/SSH session cleanly. Stop protection being disabled is not authorization to stop.

If any item fails, classify the attempt as `WORK_EC2_STOP_REQUIRES_LOCAL_DATA_REMEDIATION` and do not stop.

## Stop (future approval only)

From a different authenticated control host/session that will survive the stop:

```bash
aws ec2 stop-instances \
  --instance-ids i-0add395a2d89805b5 \
  --region eu-west-2
```

Wait for `stopped` and confirm only after the command has returned. Do not terminate the instance or detach/delete its EBS volume.

## Start (future approval only)

```bash
aws ec2 start-instances \
  --instance-ids i-0add395a2d89805b5 \
  --region eu-west-2
```

Wait for `running` and both EC2 status checks to pass. Then verify:

- new public IPv4/public DNS and expected private IPv4;
- SSH/SSM reachability and any allowlist or DNS update required;
- restore the instance-role environment and verify identity:

  ```bash
  unset AWS_EC2_METADATA_DISABLED
  unset AWS_PROFILE AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
  export AWS_REGION=eu-west-2
  export AWS_DEFAULT_REGION=eu-west-2
  aws sts get-caller-identity
  aws configure get region
  ```

  The result must be account `557604519341` and assumed role `instanceRoleTerraform`.
- root EBS mount, repository existence/status, disk free space, and local ignored configuration paths (without printing values);
- recovery-manifest size and SHA-256 matches for every critical local file;
- Docker daemon, expected images/volumes, and no unexpected containers;
- no stale Terraform plan is treated as current; always create/review a fresh plan for future work.

## Operating options

- Option A — always on: maximum convenience, about `$40.89/month` before transfer/CPU-credit variation.
- Option B — manual start/stop for work: recommended after the stop gate is remediated. At 160 running hours/month, compute plus public IPv4 plus persistent EBS is about `$11.14/month`, saving about `$29.75/month` versus 730 hours.
- Option C — scheduled stop: potentially similar or larger savings, but requires separately approved EventBridge/SSM/automation design, ownership, exceptions, and recovery testing.

An Elastic IP is not currently required if operators can discover the new address after start. Adding one solely to avoid the address change reduces the savings and creates an allocation that must be governed; it requires separate approval.

## Backup decision

- A — EBS only: sufficient for normal stop/start, zero migration effort, but no protection from volume loss or accidental termination (`DeleteOnTermination=true`).
- B — encrypted snapshot recovery: recommended near-term DR control. Because the source volume is unencrypted, implementation must use a separately approved procedure that produces and verifies an encrypted copy and controls/deletes any transient unencrypted snapshot. A full 30 GiB snapshot is roughly `$1.50/month` at a representative `$0.05/GB-month`; incremental billed size may be lower.
- C — move local-only configuration to Secrets Manager/SSM/S3: strongest centralized lifecycle and audit option, but requires secret reads/writes, IAM design, restore tooling, and separate approval. It is the long-term option, not a prerequisite implementation in this read-only task.

Choose B before manual stop approval, then evaluate C as a separate credential/configuration lifecycle project. Option A alone preserves data across stop/start but does not close the documented DR gap.

Option B was validated on 2026-08-12: the encrypted snapshot completed and an actual read-only restore matched all six manifest files by size and SHA-256. The temporary restore volume was deleted. Retain `snap-0da911dd9bd13c867`; do not use the failed copy artifact `snap-000caea04ca81bfef`. Source cleanup and EC2 stop remain separate approval gates.

## Approved-backup procedure template

This is a command review, not standing authorization. Snapshot creation, copying, attaching, and deletion each require the next human approval. Run the mutating commands only from a control session that will not be interrupted, after local Docker/PostgreSQL/build/test/Codex work is quiesced and `sync` has completed.

```bash
export AWS_REGION=eu-west-2 AWS_DEFAULT_REGION=eu-west-2
BACKUP_STAMP=$(date -u +%Y%m%d-%H%M%S)
SOURCE_NAME="system-navigator-work-ec2-pre-stop-${BACKUP_STAMP}"
ENCRYPTED_NAME="system-navigator-work-ec2-pre-stop-encrypted-${BACKUP_STAMP}"

SOURCE_SNAPSHOT_ID=$(aws ec2 create-snapshot \
  --volume-id vol-09baf3dfa613ea20d \
  --description "$SOURCE_NAME" \
  --tag-specifications "ResourceType=snapshot,Tags=[{Key=Name,Value=${SOURCE_NAME}},{Key=Purpose,Value=work-ec2-pre-stop-source}]" \
  --region eu-west-2 \
  --query SnapshotId --output text)

aws ec2 wait snapshot-completed \
  --snapshot-ids "$SOURCE_SNAPSHOT_ID" \
  --region eu-west-2

ENCRYPTED_SNAPSHOT_ID=$(aws ec2 copy-snapshot \
  --source-region eu-west-2 \
  --source-snapshot-id "$SOURCE_SNAPSHOT_ID" \
  --encrypted \
  --kms-key-id alias/aws/ebs \
  --description "$ENCRYPTED_NAME" \
  --tag-specifications "ResourceType=snapshot,Tags=[{Key=Name,Value=${ENCRYPTED_NAME}},{Key=Purpose,Value=work-ec2-pre-stop-encrypted}]" \
  --region eu-west-2 \
  --query SnapshotId --output text)

aws ec2 wait snapshot-completed \
  --snapshot-ids "$ENCRYPTED_SNAPSHOT_ID" \
  --region eu-west-2

aws ec2 describe-snapshots \
  --snapshot-ids "$SOURCE_SNAPSHOT_ID" "$ENCRYPTED_SNAPSHOT_ID" \
  --region eu-west-2 \
  --query 'Snapshots[].{Id:SnapshotId,State:State,Encrypted:Encrypted,KmsKeyId:KmsKeyId,Size:VolumeSize,Description:Description}'
```

Required result: the copy is `completed`, encrypted, 30 GiB, and uses `alias/aws/ebs`'s resolved AWS-managed key. Do not delete the unencrypted source yet.

### Restore verification template

With separate approval, create a 30 GiB encrypted gp3 volume in the work instance's AZ, attach it as a secondary device, discover its actual NVMe device with `lsblk`, and mount it read-only. Do not assume `/dev/sdf` is the Linux device name.

```bash
RESTORE_VOLUME_ID=$(aws ec2 create-volume \
  --snapshot-id "$ENCRYPTED_SNAPSHOT_ID" \
  --availability-zone eu-west-2c \
  --volume-type gp3 --size 30 --iops 3000 --throughput 125 \
  --encrypted --kms-key-id alias/aws/ebs \
  --tag-specifications "ResourceType=volume,Tags=[{Key=Name,Value=work-ec2-restore-test},{Key=Purpose,Value=temporary-restore-test}]" \
  --region eu-west-2 \
  --query VolumeId --output text)
aws ec2 wait volume-available --volume-ids "$RESTORE_VOLUME_ID" --region eu-west-2
aws ec2 attach-volume --volume-id "$RESTORE_VOLUME_ID" \
  --instance-id i-0add395a2d89805b5 --device /dev/sdf --region eu-west-2
```

After `lsblk -f` identifies the restored partition, mount it using filesystem-appropriate read-only/no-journal-replay options (for the observed ext4 root, `ro,noload`) at a new empty mount point. Then run:

```bash
python3 scripts/verify_work_ec2_recovery.py \
  --manifest quality-results/work-ec2-recovery-manifest.json \
  --restored-repository /mnt/work-ec2-restore/home/ubuntu/ai-platform
```

Also confirm the repository is readable and the expected Docker/local configuration paths exist, without printing secret contents. Passing output must be `RESTORE_FILE_HASHES_PASS` for all six files.

Cleanup requires another explicit approval: unmount, detach, wait for `available`, delete the temporary restore volume, verify deletion, and check for any temporary test instance/security group. Only after encrypted-copy metadata and restore tests pass should deletion of the unencrypted source snapshot be separately approved. Retain the encrypted recovery snapshot.

```bash
sudo umount /mnt/work-ec2-restore
aws ec2 detach-volume --volume-id "$RESTORE_VOLUME_ID" --region eu-west-2
aws ec2 wait volume-available --volume-ids "$RESTORE_VOLUME_ID" --region eu-west-2
aws ec2 delete-volume --volume-id "$RESTORE_VOLUME_ID" --region eu-west-2
aws ec2 describe-volumes --volume-ids "$RESTORE_VOLUME_ID" --region eu-west-2
```

The final describe should return `InvalidVolume.NotFound`. In a later, separately approved cleanup after restore success:

```bash
aws ec2 delete-snapshot --snapshot-id "$SOURCE_SNAPSHOT_ID" --region eu-west-2
```

Never delete `ENCRYPTED_SNAPSHOT_ID` as part of temporary-resource cleanup.
