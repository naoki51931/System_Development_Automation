# Work EC2 local-data remediation — 2026-08-12 UTC

No AWS resource or secret value was changed. Start identity was account `557604519341`, region `eu-west-2`, role `instanceRoleTerraform`, at clean HEAD `4ec5776fa6f8a90b31eb557f47ed98a3d00aa51a`.

## Inventory and classifications

Six ignored Terraform configuration files are `CRITICAL_RECOVERY_REQUIRED` and `SECRET_BEARING`: Production, Staging, and staging-prerequisites `backend.hcl`/`terraform.tfvars`. Each is covered by the non-secret recovery manifest with path, size, mtime and SHA-256. `git check-ignore -v` confirmed all six are ignored; none is tracked. The secret scanner found no current-tree or history finding.

Saved `*.tfplan` and `*-plan.txt` files are either `STALE_INVALID` after apply/partial apply or `REGENERABLE` from current state. They are not recovery inputs and must never be committed. Generated caches (`.terraform`, Playwright, npm/pip, Ruff/pytest, coverage, frontend build output, Python bytecode, Docker images/build cache) are `REGENERABLE` and `NON_SECRET` unless a future inspection proves otherwise. Docker PostgreSQL volumes total about 453 MB and persist on EBS; treat them as local-test data requiring owner confirmation before any cleanup. Quality evidence and repository scripts intended for retention are Git-tracked.

The repository is 4.0 GiB. Large areas are `environment/` 2.6 GiB (primarily provider/work directories), Playwright cache 1.2 GiB, `bootstrap/` 845 MiB, `frontend/` 655 MiB, npm cache 254 MiB, Docker build cache 2.807 GiB, and multiple unused images. These are cleanup candidates but nothing was deleted. Root is 28 GiB with 26 GiB used and 2.7 GiB free (91%). This is below the readiness script's 95% hard block, but cleanup should be separately approved before further large builds.

## Persistence, access and recovery

The running `t3.medium` has EBS root `vol-09baf3dfa613ea20d`, 30 GiB gp3, unencrypted, attached as `/dev/sda1` in `eu-west-2c`, with `DeleteOnTermination=true`. The instance type has no instance store. AWS documents that attached EBS data and private IP persist across stop/start, while an auto-assigned public IPv4 is released and a new address is assigned on start. There is no EIP.

Consequences: SSH must use the new address/DNS; known_hosts may need a new host entry; IP allowlists or DNS pointing at the old address require review. GitHub access and the EC2 instance-role trust are not inherently bound to the public IP, though an organization allowlist could be. No fixed-IP requirement was proven, so an EIP is not recommended without a separate operational requirement.

IMDSv2 is enabled and the attached profile is `instanceRoleTerraform`. The runbook resets conflicting environment credentials, restores `eu-west-2`, then verifies STS identity after start.

## Backup options and decision

- A, EBS-only: fastest and sufficient for normal stop/start, with no secret movement, but no independent recovery from volume loss/termination.
- B, encrypted snapshot recovery: recommended before stop approval. For the unencrypted source volume, use a separately approved encrypted-copy workflow, verify restore/hash recovery, and tightly control any transient unencrypted snapshot. Approximate full-size storage is `$1.50/month`; incremental usage may be lower.
- C, Secrets Manager/SSM/encrypted S3: strongest long-term configuration lifecycle, but requires secret operations, IAM/restore design, and recurring service/API cost. It was not performed.

The manifest deliberately retains its original `external_backup_verified=false` input. The separately approved live backup workflow has now produced completed unencrypted source snapshot `snap-09251b0d48de70d17` and completed encrypted recovery snapshot `snap-0da911dd9bd13c867`, using `alias/aws/ebs`. A read-only restore test matched all six manifest files by existence, size, and SHA-256, and its temporary volume was deleted. The first premature copy `snap-000caea04ca81bfef` remains a retained, unused error artifact. Evidence is in `quality-results/work-ec2-encrypted-backup-apply-result.{md,json}`. Decision: **WORK_EC2_ENCRYPTED_BACKUP_VALIDATED / WORK_EC2_READY_FOR_MANUAL_STOP_APPROVAL**. Snapshot cleanup and EC2 stop still require separate human approvals.

The final related suite passed 34 tests. Ruff check/format, Bandit, compileall, pip-audit (0 known vulnerabilities), JSON validation and the repository secret scan passed; the quality image retains pip `26.1.2`. No secret value was emitted by the checker or tests.

## Cost scenarios

Using 730 hours, compute `$0.0472/hour`, public IPv4 `$0.005/hour`, and persistent EBS `$2.784/month`:

| Usage | Estimated monthly cost | Saving vs always-on |
|---|---:|---:|
| Always on | `$40.89` | — |
| 160 hours | `$11.14` | `$29.75` |
| 80 hours | `$6.96` | `$33.93` |
| 40 hours | `$4.87` | `$36.02` |
| Fully stopped | `$2.78` | `$38.11` |

An auto-assigned public IPv4 is released on stop, so its charge stops; EBS storage continues. Maximum combined saving is approximately `$300.11–303.11/month`: Staging `$206–208`, Production `$56–57`, and work EC2 `$38.11`.

## Production wait state

Production RDS remains `available`, current `db.t4g.medium`, pending `db.t4g.small`, Multi-AZ. No RDS action or new plan was performed. The existing post-maintenance verifier still covers RDS safety, PITR/snapshot, ECS, alarms/SNS, ALB/NAT and Staging. After the pending class clears, run it and then create/review a fresh Terraform convergence plan; `0/0/0/0` is required. Current decision: **RDS_DOWNSIZING_STILL_PENDING_MAINTENANCE**.
