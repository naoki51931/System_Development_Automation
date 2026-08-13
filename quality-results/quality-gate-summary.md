# Quality gate summary — 2026-08-06 UTC resume remediation

Local-only verification resumed at baseline `22d9480e63f2246b40e7e84bea8c1206e223adbc` with the preserved uncommitted work. No GitHub push, AWS change, RDS connection, Terraform plan/apply, ECR push, migration outside local Compose, or external provider access occurred.

| Gate | Result | Evidence |
|---|---|---|
| Git diff / Terraform fmt | PASS | `git diff --check`; recursive fmt check |
| Terraform validate | PASS | Bootstrap, production, staging, and staging-prerequisites |
| Terraform safety | PASS | 16 passed, 1 skipped (provider-schema test), 121 deselected |
| Backend Test | PASS | 140 passed, 0 failed on local Compose PostgreSQL |
| Backend Overall Coverage | PASS | 83.09%; minimum 80% |
| Critical Service Coverage | PASS | 90.86% (1560/1717); minimum 90% |
| Frontend Test / Coverage | PASS | 34/34; statements/lines 85.18%, branches 74.13%, functions 81.81% |
| Ruff | PASS | check, format check, compileall |
| Security / Secret Scan | PASS | Bandit 0; pip-audit 0; secret scan 0 |
| Migration | PASS | `8d4f2a7c9b11`; downgrade, upgrade, offline SQL, metadata drift zero |
| OpenAPI | PASS | generated client check, no drift |
| Compose | PASS | no-cache build; postgres/backend/frontend/worker healthy |
| Worker Dispatch / Heartbeat / Health | PASS | registry, owner/lease CAS, healthy worker |
| Document Resume | PASS | deterministic version/key, storage hash, missing-snapshot fail-closed |
| AI Workflow Resume | PASS | deterministic run/version/review/cost, source/comment hashes |
| Resume Concurrency | PASS | claim/step idempotency, lease ownership, dead-letter guards |
| Snapshot Immutability | PASS | DB triggers reject snapshot/completed-step mutation |
| Billing Idempotency | PASS | targeted estimate/AI cost/artifact value suite: 36 passed |
| Chromium / Firefox / WebKit | PASS | 23/23 each |
| Accessibility | PASS | 12 routes/browser; axe critical 0, serious 0 |
| npm Audit | PASS | runtime `--omit=dev`: 0 vulnerabilities; nanoid pinned to 3.3.17 |
| Local Images | PASS | app and frontend linux/amd64, non-root, healthchecks present |
| Staging App Image Remediation | PASS | ECR `sha256:d92639685a9a455361b55cfe344112154cf05787bd28f4d10352bfb861f9e9e8`: CRITICAL 0, HIGH 0, MEDIUM 0; 142 tests, 82.89% overall, 90.86% critical-service, pip-audit/Bandit pass |
| Staging Notifications | PASS | SNS email variable, manual confirmation, alarms complete; Budget 100 GBP |
| Prerequisite Root Boundary | PASS | ECR/IAM/SNS/Budget retained; custom-domain ACM/DNS disabled; explicit one-way main inputs |
| Performance | PASS | retained 50-user/60-second: 0% errors, detail p95 490 ms, list p95 540 ms |
| Production 100 RPM pre-apply | READY_WITH_MANUAL_SNS_CONFIRMATION_REQUIRED | Recipient is planned on an isolated topic; pip 25.0.1 tool findings are remediated by pinned 26.1.2 and runtime pip removal. Security/tests pass. Final plan is 19-add/3-change/0-replace/0-destroy. No apply authorized. |
| Documentation | PASS | seven requested documents synchronized |

The Compose-profile E2E attempt first failed because its quality image lacked browser binaries and its API default was container-local `localhost`. It was rerun against the same healthy Compose stack using the existing host Playwright 1.62.1 cache; all 69 tests passed.

## Current domain decision

`true-camera-test.com` is not used. No replacement custom domain is selected. ACM, Route53 staging records and HTTPS remain disabled; temporary staging access is limited to the ALB HTTP DNS name under mock-only, non-sensitive restrictions. Notifications remain `info@nagi-neco.com` and the monthly Budget remains 100 GBP.

Every mandatory pre-plan local gate is PASS. This authorizes only human review of prerequisite resource scope. Terraform plan/apply, AWS changes, ECR/GitHub push, image digest capture, RDS access/migration, and staging deployment remain prohibited pending the documented approvals and human inputs.

## 2026-08-10 staging bootstrap reconciliation

The empty Cloud Map `health_check_custom_config {}` block was the sole cause of backend/worker ForceNew drift after bootstrap. It was removed without `ignore_changes`; four Terraform roots validate, 17 staging Terraform safety tests pass, and the saved reconcile plan is `No changes` with both discovery resources no-op and add/change/replace/destroy all zero. Production resources remain active/available, the application DB Secret has zero versions, and runtime ECS services remain zero.

RDS is available with the reviewed low-cost and protection settings. Its latest restorable timestamp is `2026-08-10T14:16:14Z`, but the earliest timestamp and automated-backup restore window are still null. Final status is `WAITING_FOR_RDS_PITR_PROTECTION`; Secret registration, snapshot, migration, and runtime services remain separately approval-gated.

## 2026-08-12 Production PITR and final-plan remediation

Production PITR Gate is PASS. `DBInstance.EarliestRestorableTime` is null and retained as `PITR_API_FIELD_WARNING`; the matching active automated-backup record has 14-day retention and a complete ordered restore window, the latest automated snapshot and named manual snapshot are available/encrypted, and recent backup failures are zero.

Backend is 167 passed with 82.89% overall and 90.86% critical-service coverage. Frontend is 34 passed with build and OpenAPI drift checks PASS. Ruff, formatting, compileall, Bandit, pip-audit, and secret scan PASS; the quality image retains pip 26.1.2. All four Terraform roots pass recursive fmt, backend-disabled init, and validate; Terraform safety tests pass and `STAGING_IDLE_MODE_CONVERGED` remains unchanged.

The new review-only plan `production-100rpm-pitr-remediated-final.tfplan` has SHA-256 `6c4a977c54942c734526abc7f233124014a74eef861fc298f91f90b28b27efc3` and 19 add / 3 change / 0 replace / 0 destroy. RDS replacement and Production infrastructure destruction are zero. The former `production-100rpm-remediated-final.tfplan` (`d6f094d...5df0`) is **STALE / INVALID**. No apply or push occurred. Final decision: **READY_WITH_MANUAL_SNS_CONFIRMATION_REQUIRED**.

## 2026-08-12 Production apply result

The approved saved plan was applied once and partially succeeded. ECS is healthy on 256 CPU/512 MiB with autoscaling 1–2; GET smoke tests and PITR pass, ALB/NAT and Staging idle are preserved, SNS is PendingConfirmation, and seven ALB/ECS alarms are OK. AWS rejected the Multi-AZ RDS `db.t4g.small` change with `InsufficientDBInstanceCapacity`; RDS remains medium with no pending change and six RDS alarms are absent. The post-apply plan is 6 add / 1 change / 0 destroy. No retry, rollback, or push occurred. Final decision: **PRODUCTION_100RPM_DOWNSIZING_REQUIRES_REMEDIATION**.

## 2026-08-12 residual remediation review

AWS orderable options confirm PostgreSQL 18.3 `db.t4g.small` is Multi-AZ/gp2 orderable in eu-west-2a/b/c, distinguishing the prior error as temporary capacity unavailability rather than an unsupported class. The fresh residual plan SHA `992ec5ff...5578` is exactly 6 RDS alarms plus one in-place medium-to-small RDS update, with 0 replace/destroy/ECS/ALB/NAT/Staging action. PITR, snapshot, Production health, four Terraform validates and focused security/tests pass. No apply occurred. Decision: **READY_FOR_PRODUCTION_RDS_SMALL_RETRY_APPLY_APPROVAL**.

The checksum-approved residual plan was subsequently applied exactly once: 6 add / 1 change / 0 destroy. RDS accepted the small class as pending maintenance, all 13 alarms exist with no ALARM state, and PITR/ECS/ALB/NAT/Staging remain healthy. The post-apply residual is only the pending RDS class transition. Decision: **PRODUCTION_100RPM_DOWNSIZING_APPLIED / RDS_DOWNSIZING_PENDING_MAINTENANCE / MANUAL_SNS_CONFIRMATION_REQUIRED**.

## 2026-08-12 work EC2 encrypted backup validation

Source snapshot `snap-09251b0d48de70d17` completed unencrypted at 30 GiB. Replacement snapshot `snap-0da911dd9bd13c867` completed encrypted with the AWS-managed EBS key. An actual same-AZ secondary-volume restore was mounted ext4 `ro,noload`; Git was readable and all six critical local files matched the recovery manifest by existence, size, and SHA-256. Temporary volume `vol-045b7e4095e33d4af` was unmounted, detached without force, and deleted. The work EC2 remains running with 2/2 checks and unchanged root EBS. The earlier failed copy remains an unused retained artifact. Decision: **WORK_EC2_ENCRYPTED_BACKUP_VALIDATED / WORK_EC2_READY_FOR_SOURCE_SNAPSHOT_CLEANUP_APPROVAL / WORK_EC2_READY_FOR_MANUAL_STOP_APPROVAL**.

Production RDS remains `db.t4g.medium` with `db.t4g.small` pending maintenance; no Production change or post-maintenance verifier run occurred. Decision: **RDS_DOWNSIZING_STILL_PENDING_MAINTENANCE**.

## 2026-08-13 work EC2 manual-stop pre-execution gate

AWS account/region/role, clean worktree, completed source and encrypted recovery snapshots, enabled AWS-managed EBS key, prior actual restore PASS, and current 6/6 critical-file size/SHA-256 matches are confirmed. Docker has zero running containers, local PostgreSQL is inactive, and no critical writer exists besides the explicitly authorized Codex/SSH control session. Root EBS `vol-09baf3dfa613ea20d` remains the attached 30 GiB gp3 root and stop protection is clear. Public IPv4 `18.170.41.191` is not an EIP and is expected to be released. Decision: **STOP_COMMAND_AUTHORIZED / STOP_EXECUTION_PENDING / WORK_EC2_READY_FOR_MANUAL_STOP**.

Production RDS remains `db.t4g.medium` with `db.t4g.small` pending maintenance. Decision: **RDS_DOWNSIZING_STILL_PENDING_MAINTENANCE**.
