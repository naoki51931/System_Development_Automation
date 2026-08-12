# Work EC2 cost and stop readiness — 2026-08-12 UTC

No EC2 stop/start or other AWS resource change was performed.

## Inventory and persistence

`i-0add395a2d89805b5` is a running `t3.medium` in `eu-west-2c`, VPC `vpc-09fe8054e761e54ca`, subnet `subnet-09636511a5d33c952`. Both EC2 status checks are OK. It uses private IPv4 `172.31.0.175` and auto-assigned public IPv4 `18.170.41.191`; the subnet maps public IPs on launch and no Elastic IP is associated. Stop/start is therefore expected to change public IPv4/public DNS, affecting SSH, allowlists, DNS, or integrations that pinned the current address.

The root device is one attached, unencrypted 30 GiB gp3 EBS volume `vol-09baf3dfa613ea20d` (3000 IOPS, 125 MiB/s), with `DeleteOnTermination=true`. No owner snapshot exists. `t3.medium` has no instance store. The repository, `/home/ubuntu`, Docker root and four Docker volumes are on the root EBS and persist across stop/start; `/tmp` is tmpfs and does not. Root disk utilization was 91% (2.7 GiB free).

The instance profile is `instanceRoleTerraform`; IMDSv2 tokens are required. Termination and stop protection are both disabled. Docker has no running container. The only relevant active long-running work at inspection was the current Codex session; no Terraform apply, Docker build, migration, local PostgreSQL, pytest, Playwright, or application server was observed.

## Local-only file risk

The following ignored files exist and must be preserved without exposing their contents:

- `environment/backend.hcl`, `environment/terraform.tfvars`
- `environment/staging/backend.hcl`, `environment/staging/terraform.tfvars`
- `environment/staging-prerequisites/backend.hcl`, `environment/staging-prerequisites/terraform.tfvars`

Treat these as secret-bearing/must-preserve. Numerous ignored `*.tfplan` and `*-plan.txt` files also exist. Convergence plans are regenerable; already applied or partially applied saved plans are stale/invalid and must never be reapplied. The worktree was clean, but Git does not protect these ignored files. Because there is no EBS snapshot or verified separate secure recovery copy, local-data recovery remains the stop-readiness gap even though a normal stop preserves EBS.

## Cost and strategy

Configuration-based steady-state cost is approximately `$34.46` compute + `$2.78` gp3 EBS + `$3.65` public IPv4 = **$40.89/month**, excluding data transfer and CPU-credit variation. When stopped, compute and the auto-assigned public IPv4 charge cease; EBS remains approximately **$2.78/month**. Maximum full-month saving is therefore about **$38.11/month**.

At 160 running hours/month, manual start/stop costs approximately `$7.55` compute + `$0.80` public IPv4 + `$2.78` EBS = **$11.14/month**, saving about **$29.75/month**. Always-on maximizes convenience. A schedule could save more but requires separately approved automation and exception handling. An Elastic IP is not recommended solely for this workstation unless a stable allowlisted address is operationally mandatory.

The recommended strategy is manual start/stop after: (1) securely backing up or otherwise proving recoverability of local-only configuration, (2) ending all SSH/Codex jobs, and (3) accepting/documenting the public-IP change. See `docs/work_ec2_stop_start_runbook.md`.

Documentation JSON validation and the repository secret scan passed. The Production verifier/PITR suite also passed 28 unit tests; Ruff, formatting, Bandit, compileall and pip-audit passed in the pinned quality image (pip `26.1.2`).

Decision: **WORK_EC2_STOP_REQUIRES_LOCAL_DATA_REMEDIATION**. Once secure recovery for must-preserve local-only files is verified and the runbook gate is clean, it can advance to `WORK_EC2_SAFE_FOR_MANUAL_STOP_APPROVAL`. Stopping remains a separate human-approved action.
