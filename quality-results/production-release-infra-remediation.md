# Production release infrastructure remediation evidence

Date: 2026-08-15 UTC

- Remediation base HEAD: `d47af37fcac3192957f7b76769573076da9e2dfb`
- Starting branch: `agent/production-release-infra-remediation`
- Starting upstream divergence: `HEAD...origin/agent/production-release-infra-remediation = 0 0`
- AI review BLOCKER — migration gate was a diagnostic check/self-declared digest. Fix: verifier-produced structured evidence plus a root `terraform_data` lifecycle precondition and backend/frontend/worker service preconditions. Semantic tests prove missing evidence and digest mismatch fail planning, valid evidence passes, and runtime disabled preserves the existing backend service.
- AI review HIGH — migration success proof was self-attested. Fix: read-only ECS verifier validates fixed Production boundaries, exact task/task-definition revision, migration command, STOPPED state/reason, essential exit zero, and resolved digest; unit tests cover each failure class. Alembic head comes from a separately approved Production DB verification task step; no DB connection occurred here. Remaining risk: Terraform cannot independently authenticate arbitrary operator input, so the controlled release workflow and reviewed verifier artifact are the procedural trust boundary.
- AI review HIGH — account/region/repository could move together. Fix: literal account `557604519341`, region `eu-west-2`, and repository names; provider `allowed_account_ids`; semantic validation cases cover wrong account/region/repository, tag/latest, short/malformed/uppercase digest, and valid digest.
- AI review HIGH — worker custom alarms had no producer. Fix: application `PutMetricData` producer with exact namespace/names/dimensions, constant non-secret failure logging, worker-only namespace-constrained IAM, and mocked application contract tests.
- AI review MEDIUM — worker memory monitoring missing. Fix: 80% average `AWS/ECS MemoryUtilization`, two 300-second periods, ClusterName/ServiceName dimensions, and Production SNS actions.
- AI review MEDIUM — frontend lifecycle missing. Fix: retain 20 tagged releases, clean untagged images after seven days, immutable tags, scan-on-push, and AES256 encryption.
- AI review LOW — shared security group. Disposition: `FOLLOW_UP_SECURITY_HARDENING`; no split without live state/plan evidence because preserving the existing Production backend/RDS/ALB is higher priority.
- Backend: 210 passed; overall coverage 83.04%; critical-service aggregate 90.86%
- Ruff: PASS
- Ruff format: PASS
- Bandit: PASS with a documented `B105` false-positive suppression for the JWT `token_use` discriminator
- pip-audit: PASS, zero known vulnerabilities
- secret scan: PASS
- Frontend unit: 34 passed; coverage 79.03% statements/lines, 72.88% branches, 81.81% functions
- Frontend OpenAPI drift: PASS
- Frontend typecheck: PASS
- Frontend build: PASS
- npm audit: PASS, zero vulnerabilities after safe lock updates for nanoid/js-yaml
- Terraform fmt: PASS
- Terraform validate: PASS for `bootstrap`, `environment`, `environment/staging`, and `environment/staging-prerequisites`
- Terraform release/static safety tests: included in the 210-test backend suite. Native `terraform test` mock-provider semantics: 10 passed, covering missing attestation hard failure, digest mismatch hard failure, valid pass, wrong account/region/repository, tag/latest, short/uppercase digest, disabled-runtime backend preservation, and release topology.
- `git diff --check`: PASS before commits
- AWS changes: none
- Terraform apply/destroy: not run
- Migration: not run
- Production DB: not connected
- Deployment: not run
- External launch ready: false

External blockers remain: `COGNITO_NOT_WIRED`, `HTTPS_DNS_NOT_WIRED`, `AI_PROVIDER_NOT_WIRED`, `PAYMENT_PROVIDER_NOT_WIRED`, `EMAIL_PROVIDER_NOT_WIRED`, and unverified `RDS_PENDING_MAINTENANCE`.

The implementation is ready for GitHub CI review only. It is not Production deploy approval.
