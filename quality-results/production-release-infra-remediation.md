# Production release infrastructure remediation evidence

Date: 2026-08-15 UTC

- Remediation base HEAD: `d47af37fcac3192957f7b76769573076da9e2dfb`
- Starting branch: `agent/production-release-infra-remediation`
- Starting upstream divergence: `HEAD...origin/agent/production-release-infra-remediation = 0 0`
- AI review BLOCKER — migration gate was a diagnostic check/self-declared digest. Fix: verifier-produced structured evidence plus a root `terraform_data` lifecycle precondition and backend/frontend/worker service preconditions. Semantic tests prove missing evidence and digest mismatch fail planning, valid evidence passes, and runtime disabled preserves the existing backend service.
- AI review HIGH — migration attestation authenticity/release binding was insufficient. Fix: canonical schema-v1 JSON is sorted/compact and excludes checksum/signature from its payload; the read-only verifier recomputes SHA-256, verifies an Ed25519 signature and approved signing identity, binds `release_sha`/`github_sha` to the approved post-merge `master` SHA and fixed workflow/job, enforces fixed Production ECS/ECR boundaries, Alembic provenance, and 24-hour freshness (5-minute skew). Tampering, unsigned/invalid signatures, stale/future timestamps, duplicate JSON keys, unsupported schema, provenance mismatch, or release mismatch fail closed. The protected release workflow generates and stores the signed artifact outside the repository; Terraform consumes only the verifier-produced artifact and applies structural hard preconditions. No Production DB connection occurred here.
- AI review HIGH — account/region/repository could move together. Fix: literal account `557604519341`, region `eu-west-2`, and repository names; provider `allowed_account_ids`; semantic validation cases cover wrong account/region/repository, tag/latest, short/malformed/uppercase digest, and valid digest.
- AI review HIGH — worker custom alarms had no producer. Fix: application `PutMetricData` producer with exact namespace/names/dimensions, constant non-secret failure logging, worker-only namespace-constrained IAM, and mocked application contract tests.
- AI review MEDIUM — worker memory monitoring missing. Fix: 80% average `AWS/ECS MemoryUtilization`, two 300-second periods, ClusterName/ServiceName dimensions, and Production SNS actions.
- AI review MEDIUM — frontend lifecycle missing. Fix: retain 20 tagged releases, clean untagged images after seven days, immutable tags, scan-on-push, and AES256 encryption.
- AI review LOW — shared security group. Disposition: `FOLLOW_UP_SECURITY_HARDENING`; no split without live state/plan evidence because preserving the existing Production backend/RDS/ALB is higher priority.
- Backend: full suite and coverage rerun after attestation remediation (see final validation output); prior baseline was 210 passed, 83.04% overall, 90.86% critical aggregate.
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
- Terraform release/static safety tests: native `terraform test` mock-provider semantics cover missing/unsigned attestation, release-SHA and digest mismatch, valid pass, wrong account/region/repository, tag/latest and malformed digest, disabled-runtime backend preservation, and release topology.
- `git diff --check`: PASS before commits
- AWS changes: none
- Terraform apply/destroy: not run
- Migration: not run
- Production DB: not connected
- Deployment: not run
- External launch ready: false

External blockers remain: `COGNITO_NOT_WIRED`, `HTTPS_DNS_NOT_WIRED`, `AI_PROVIDER_NOT_WIRED`, `PAYMENT_PROVIDER_NOT_WIRED`, `EMAIL_PROVIDER_NOT_WIRED`, and unverified `RDS_PENDING_MAINTENANCE`.

The implementation is ready for GitHub CI review only. It is not Production deploy approval.
