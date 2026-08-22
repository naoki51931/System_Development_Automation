# Production release infrastructure remediation evidence

Date: 2026-08-15 UTC

- Remediation base HEAD: `d47af37fcac3192957f7b76769573076da9e2dfb`
- Starting branch: `agent/production-release-infra-remediation`
- Starting upstream divergence: `HEAD...origin/agent/production-release-infra-remediation = 0 0`
- AI review BLOCKER — migration gate was a diagnostic check/self-declared digest. Fix: verifier-produced structured evidence plus a root `terraform_data` lifecycle precondition and backend/frontend/worker service preconditions. Semantic tests prove missing evidence and digest mismatch fail planning, valid evidence passes, and runtime disabled preserves the existing backend service.
- AI review HIGH — migration attestation authenticity/release binding was insufficient. Fix: canonical schema-v1 JSON is sorted/compact and excludes checksum/signature from its payload; the read-only verifier recomputes SHA-256, verifies an Ed25519 signature and approved signing identity, binds `release_sha`/`github_sha` to the approved post-merge `master` SHA and fixed workflow/job, enforces fixed Production ECS/ECR boundaries, Alembic provenance, and 24-hour freshness (5-minute skew). Tampering, unsigned/invalid signatures, stale/future timestamps, duplicate JSON keys, unsupported schema, provenance mismatch, or release mismatch fail closed. The protected release workflow generates and stores the signed artifact outside the repository; Terraform consumes only the verifier-produced artifact and applies structural hard preconditions. No Production DB connection occurred here.
- Fourth remediation HIGH-1 — Production verification now loads a closed, single-key Ed25519 trust root only from `config/production_migration_attestation_trust.json`; public-key/key-id CLI overrides were removed. Unknown keys, wrong algorithms, invalid base64/key length, extra/null/duplicate fields, attacker signatures, and artifact key substitution fail closed. The test-only private seed is cryptographically separate from the Production public key.
- Fourth remediation HIGH-2 — the earlier fixed-path handoff and gate-target plan were an intermediate state. Fifth remediation below supersedes both with isolated tests, a trusted producer-run check, secure same-job handoff, and full saved plan. No apply/deploy step exists and pull requests cannot invoke either Production workflow.
- Fourth remediation HIGH-3 — free-form Alembic CLI provenance was removed. A closed read-only evidence schema fixes release/account/region/task/task-definition/exit/head/timestamp/output checksum and GitHub workflow/job/ref/run identity; its canonical SHA-256 is covered by the signed migration payload.
- Fourth remediation MEDIUM-1 — attestation schema v2 is an exact-field, non-null, strict-type closed schema. Duplicate keys, NaN/Infinity, non-ASCII/non-NFC schema strings, malformed hashes and non-canonical RFC3339 UTC timestamps are rejected; two stable canonical SHA-256 vectors and tamper cases are tested.
- Fourth remediation MEDIUM-2 — normal CI now runs `terraform -chdir=environment test` after safe backend-free initialization using mock providers and an ignored TEST ONLY handoff. Production workflow runs the same native gate before plan preparation.
- Fifth remediation BLOCKER-1 — deleted the live-path test handoff writer and moved native cases to `tests/terraform/production_release_gate_fixture`. The fixture is not a child of the Production root, uses no Production handoff path/key, and covers valid/disabled plus fake, unsigned, wrong-key, non-zero, Alembic mismatch, stale, future, and missing cases.
- Fifth remediation HIGH-1 — the consumer runs verifier/trust code only from a control-plane checkout fixed to `github.sha`, current `origin/master`, and protected `master`; the release tree is a separate checkout of the identical SHA. No workflow input selects release SHA, verifier path, trust config, key, or artifact path.
- Fifth remediation HIGH-2 — `.github/workflows/production-migration-evidence.yml` is the protected machine producer. It derives migration/verification task identity, definition revision, exit, digest, and Alembic result from AWS APIs/exact log output; signs with only the protected Environment secret; self-verifies; and uploads a fixed artifact. The consumer independently verifies the successful run identity and conclusion through GitHub API. This producer was not executed during remediation.
- Fifth remediation HIGH-3 — the consumer re-verifies freshness and then creates a full saved Production plan without `-target`. Metadata binds release SHA, app/frontend digests, attestation/Alembic/verifier receipts, plan SHA-256, and add/change/replace/destroy totals. The plan is AES-256-GCM encrypted with a protected Environment key before artifact upload. No apply job exists; a future apply must decrypt and consume the reviewed plan with matching metadata without replanning.
- Fifth remediation MEDIUM — a fixed canonical bytes/SHA/public-key/signature vector and tamper case are checked in; native negative semantics run in required CI; all Production trust-path third-party Actions are immutable commit-SHA pinned.
- AI review HIGH — account/region/repository could move together. Fix: literal account `557604519341`, region `eu-west-2`, and repository names; provider `allowed_account_ids`; semantic validation cases cover wrong account/region/repository, tag/latest, short/malformed/uppercase digest, and valid digest.
- AI review HIGH — worker custom alarms had no producer. Fix: application `PutMetricData` producer with exact namespace/names/dimensions, constant non-secret failure logging, worker-only namespace-constrained IAM, and mocked application contract tests.
- AI review MEDIUM — worker memory monitoring missing. Fix: 80% average `AWS/ECS MemoryUtilization`, two 300-second periods, ClusterName/ServiceName dimensions, and Production SNS actions.
- AI review MEDIUM — frontend lifecycle missing. Fix: retain 20 tagged releases, clean untagged images after seven days, immutable tags, scan-on-push, and AES256 encryption.
- AI review LOW — shared security group. Disposition: `FOLLOW_UP_SECURITY_HARDENING`; no split without live state/plan evidence because preserving the existing Production backend/RDS/ALB is higher priority.
- Backend: 234 passed after fifth remediation; 82.55% overall and 90.69% critical-service aggregate coverage.
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
- Terraform release/static safety tests: isolated native `terraform test` semantics have 10 passing cases covering missing/fake/unsigned/wrong-key evidence, non-zero exit, Alembic mismatch, stale/future evidence, valid handoff, and disabled-runtime backend preservation. Four Terraform roots validate successfully.
- `git diff --check`: PASS before commits
- AWS changes: none
- Terraform apply/destroy: not run
- Migration: not run
- Production DB: not connected
- Deployment: not run
- External launch ready: false

External blockers remain: `COGNITO_NOT_WIRED`, `HTTPS_DNS_NOT_WIRED`, `AI_PROVIDER_NOT_WIRED`, `PAYMENT_PROVIDER_NOT_WIRED`, `EMAIL_PROVIDER_NOT_WIRED`, and unverified `RDS_PENDING_MAINTENANCE`.

`GITHUB_PRODUCTION_ENVIRONMENT_CONFIGURATION_REQUIRED`: required reviewers,
protected-master deployment policy, and protected Production variables,
signer, plan-encryption key, role/network/task identities
must be configured externally before a Production plan. This remains a
Production-plan blocker, not a Draft PR review blocker.

The implementation is ready for GitHub CI review only. It is not Production deploy approval.
