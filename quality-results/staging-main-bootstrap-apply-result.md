# Staging main bootstrap apply result

Date: 2026-08-10 UTC  
Applied Git HEAD: `87ee88834956d79db266c97e087d413981ac98c5`  
AWS account / region: `557604519341` / `eu-west-2`  
State key: `system-navigator/staging/terraform.tfstate`  
Applied saved plan: `/home/ubuntu/ai-platform/environment/staging/staging-main-bootstrap.tfplan`

## Apply result

The saved, previously reviewed plan was applied without regeneration. Terraform reported `73 added, 0 changed, 0 destroyed`. The state contains 79 addresses: 73 managed resources plus six data-source addresses. No backend, worker, or frontend ECS service was created.

## AWS resource verification

- Network: VPC `vpc-0b5ce4ab333cc5b7c` is available with CIDR `10.30.0.0/16`.
- Subnets: six total across `eu-west-2a` and `eu-west-2b`: two public (`10.30.0.0/24`, `10.30.1.0/24`), two private application (`10.30.10.0/24`, `10.30.11.0/24`), and two database (`10.30.20.0/24`, `10.30.21.0/24`).
- NAT gateways / staging-tagged EIPs: `0 / 0`.
- Endpoints: eight available: S3 Gateway plus private-DNS Interface endpoints for ECR API, ECR DKR, Logs, Monitoring, Secrets Manager, STS, and KMS.
- Artifact S3: `system-navigator-staging-artifacts-557604519341`; all four public-access blocks enabled, AES-256 default encryption, versioning enabled, TLS-only deny policy, seven-day incomplete multipart cleanup, 90-day noncurrent expiration. Terraform configuration retains `prevent_destroy = true`.
- RDS: `system-navigator-staging-db` is `available`, PostgreSQL, `db.t4g.small`, 20 GiB `gp3`, Single-AZ, backup retention 3 days, private, encrypted, and deletion-protected.
- Application DB Secret: the `/system-navigator/staging/database` container exists. `list-secret-version-ids` returned zero versions; no value was retrieved or registered.
- ECS: `system-navigator-staging-cluster` is active with zero active services and zero running/pending tasks.
- Task definitions: revision 1 exists for backend, worker, frontend, and migration. Backend/worker/migration use app digest `sha256:29b9f0097affcd432444f001ee951e7d86e7f18668110a130bcd666b3f8b78fe`; frontend uses digest `sha256:5c2eeeee402293fa783c9a6dd67b6f03dce00b3651ef73d314f773d3371e82dc`. Migration remains `alembic upgrade head` and was not run.
- ALB: internet-facing application ALB is active with HTTP port 80 only. Backend target health is `/health`; frontend target health is `/login`. There are no registered runtime targets.
- Custom domain: no ACM certificate, Route53 staging record, or HTTPS listener is in state.
- Logs: backend, worker, frontend, and migration groups exist with 14-day retention.
- Alarms: eight infrastructure alarms exist (ALB 5xx/response-time/two unhealthy-target and four RDS alarms). Runtime ECS CPU/memory, running-task, worker-heartbeat, and dead-letter alarms are absent.
- SNS: `system-navigator-staging-alerts` is referenced; `info@nagi-neco.com` remains `PendingConfirmation`.

## RDS protection status

The DB instance reports backup retention 3 and a top-level latest restorable time of `2026-08-10T13:56:13Z`. The automated-backup record is `active`, but its earliest and latest restorable window fields are still null immediately after creation. Initial backup/PITR protection is therefore treated as not fully established. No database connection or migration was attempted.

## Production impact

The applied saved plan contained zero production changes. The main staging state has only staging-scoped addresses. Read-only post-apply checks found the production ECS cluster, RDS instance, ALB, ECR repository, and VPC still active/available. No production mutation was performed.

## Post-apply convergence warning

The required `terraform plan -var-file=terraform.tfvars -detailed-exitcode` returned exit code 2, not 0. It proposed `2 to add, 0 to change, 2 to destroy`: replacement of the backend and worker `aws_service_discovery_service` resources because configuration contains an empty `health_check_custom_config {}` block that AWS/provider refresh omitted from state.

This follow-up plan was not saved or applied. Runtime services remain disabled. Because post-apply convergence failed and the automated-backup restore window is not fully established, database Secret approval is blocked pending a separately approved remediation/review and a later RDS protection recheck.

## Prohibited phases not performed

No Secret value was read or registered, no RDS connection or migration was attempted, `enable_runtime_services` remains false, no runtime-service plan/apply was run, and no GitHub push or production change occurred.

Decision: `NOT_READY_FOR_STAGING_DATABASE_SECRET_APPROVAL`  
Protection status: `BOOTSTRAP_CREATED_WAITING_FOR_RDS_PROTECTION`

## 2026-08-10 reconciliation follow-up

Root cause was confirmed: AWS/provider refresh does not retain the empty Cloud Map `health_check_custom_config {}` block. The block was removed from configuration without `ignore_changes`, state manipulation, import, taint, replacement, or apply. The saved reconcile plan reports `No changes`; backend and worker discovery actions are both `no-op`, with add/change/replace/destroy all zero.

RDS remains available with backup retention 3 and deletion protection enabled. `LatestRestorableTime` advanced to `2026-08-10T14:16:14Z`, but `EarliestRestorableTime` remains null and the automated-backup restore-window timestamps remain null. PITR protection is therefore still blocked. The application Secret has zero versions, runtime ECS services remain zero, and migration was not run.
