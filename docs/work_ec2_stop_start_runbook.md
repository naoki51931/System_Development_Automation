# Work EC2 stop/start runbook

Scope: `i-0add395a2d89805b5` in `eu-west-2`. This instance is an operator workstation, not a Production Terraform resource. Stop or start requires explicit human approval. The commands below are examples and were not run while preparing this document.

## Current persistence and access model

- The instance is `t3.medium` and has no instance store. `/home/ubuntu`, the repository, Docker root (`/var/lib/docker`), and Docker volumes are on the 30 GiB gp3 root EBS volume `vol-09baf3dfa613ea20d`.
- EBS persists across stop/start. `/tmp` is tmpfs and does not persist.
- The volume is unencrypted, has no owner snapshot, and has `DeleteOnTermination=true`. Stop does not delete it, but termination would.
- The current public IPv4 is auto-assigned; there is no Elastic IP. Stop/start normally releases it and assigns a different address. Private IPv4 normally remains attached to the primary network interface.
- AWS credentials come from IMDSv2 and `instanceRoleTerraform`. Do not copy temporary credentials to disk.

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

3. Inventory without printing contents: `environment/{backend.hcl,terraform.tfvars}`, equivalent Staging and staging-prerequisites files, saved plans/reviews, and local evidence. Treat tfvars/backend files as secret-bearing and must-preserve. Treat convergence plans as regenerable; treat already applied/partially applied plans as stale and never reapply them.
4. Verify an approved secure backup/recovery path for must-preserve local-only files. The current root EBS has no snapshot; do not stop on the assumption that Git contains ignored configuration.
5. Confirm no Terraform apply/plan, Docker build, migration, database test/server, pytest, Playwright/browser test, deployment, Production operational process, or SSH-dependent long job is running. `docker ps` must show no workload that must remain available.
6. Confirm the filesystem is EBS-backed, mounts are healthy, disk space is acceptable, and no required data exists only under `/tmp`.
7. Record the current public/private IPs and update the access plan. Document any SSH allowlist, DNS record, or external integration tied to the public IPv4.
8. End the active Codex/SSH session cleanly. Stop protection being disabled is not authorization to stop.

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
- `aws sts get-caller-identity`, account `557604519341`, role `instanceRoleTerraform`, and region `eu-west-2`;
- root EBS mount, repository existence/status, disk free space, and local ignored configuration paths (without printing values);
- Docker daemon, expected images/volumes, and no unexpected containers;
- no stale Terraform plan is treated as current; always create/review a fresh plan for future work.

## Operating options

- Option A — always on: maximum convenience, about `$40.89/month` before transfer/CPU-credit variation.
- Option B — manual start/stop for work: recommended after the stop gate is remediated. At 160 running hours/month, compute plus public IPv4 plus persistent EBS is about `$11.14/month`, saving about `$29.75/month` versus 730 hours.
- Option C — scheduled stop: potentially similar or larger savings, but requires separately approved EventBridge/SSM/automation design, ownership, exceptions, and recovery testing.

An Elastic IP is not currently required if operators can discover the new address after start. Adding one solely to avoid the address change reduces the savings and creates an allocation that must be governed; it requires separate approval.
