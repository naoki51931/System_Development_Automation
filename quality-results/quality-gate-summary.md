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
| Staging App Image Remediation | IN_PROGRESS | Python 3.12.13 Alpine 3.24 digest pinned after Bookworm retained Perl findings; 142 tests, 82.89% overall, 90.86% critical-service, pip-audit/Bandit pass; awaiting final immutable ECR scan |
| Staging Notifications | PASS | SNS email variable, manual confirmation, alarms complete; Budget 100 GBP |
| Prerequisite Root Boundary | PASS | ECR/IAM/SNS/Budget retained; custom-domain ACM/DNS disabled; explicit one-way main inputs |
| Performance | PASS | retained 50-user/60-second: 0% errors, detail p95 490 ms, list p95 540 ms |
| Documentation | PASS | seven requested documents synchronized |

The Compose-profile E2E attempt first failed because its quality image lacked browser binaries and its API default was container-local `localhost`. It was rerun against the same healthy Compose stack using the existing host Playwright 1.62.1 cache; all 69 tests passed.

## Current domain decision

`true-camera-test.com` is not used. No replacement custom domain is selected. ACM, Route53 staging records and HTTPS remain disabled; temporary staging access is limited to the ALB HTTP DNS name under mock-only, non-sensitive restrictions. Notifications remain `info@nagi-neco.com` and the monthly Budget remains 100 GBP.

Every mandatory pre-plan local gate is PASS. This authorizes only human review of prerequisite resource scope. Terraform plan/apply, AWS changes, ECR/GitHub push, image digest capture, RDS access/migration, and staging deployment remain prohibited pending the documented approvals and human inputs.
