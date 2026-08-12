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
