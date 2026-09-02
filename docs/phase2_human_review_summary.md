# System Navigation AI Enterprise Phase 2 — Human Review Summary

Date: 2026-09-02 UTC
Scope: Phase 1 through Phase 2 Executor Foundation, before Terraform CLI implementation.

## Decision

**ENTERPRISE_PHASE2_HUMAN_REVIEW_READY**

Static review found no SECURITY_CRITICAL_GAP_FOUND in the reviewed foundation. The final CI-equivalent verification was completed in isolated cached Python 3.12.13 / PostgreSQL 16 containers. The worktree contains the pre-existing Phase 1/2 diff plus this report; actual Terraform apply remains prohibited.

## Architecture and security guarantees

- Permission policy is deny-by-default. Unknown roles/actions/resources resolve to no permissions; `AI_AGENT` has an empty permission set.
- Organization and project access are checked before protected operations. Project membership is loaded for project-scoped permissions; cross-tenant records are rejected.
- `ProtectedApproval` is immutable in intent and binds action, tenant, project, resource, target version, plan checksum, expiry, requester, and distinct approver. Protected staging actions require four-eyes approval.
- Audit records contain sanitized metadata only. The existing database trigger remains application-level append-only (`APPLICATION_LEVEL_APPEND_ONLY`); no audit update/delete path was added.
- `DeploymentPlan` is database-constrained to staging. The security gate blocks production hints, DNS, IAM, secrets, snapshot deletion, all destroy actions, wrong account/region/state/root, and unknown context.
- `SafeStagingTerraformExecutor` only re-reads/canonicalizes the stored artifact, recomputes SHA-256, revalidates approval/gate/context/permission, and records preparation evidence. It does not launch Terraform, call AWS, or accept arbitrary commands.
- Root validation rejects absolute paths, traversal, backslashes, non-canonical paths, unallowlisted roots, and symlink escapes.

## Requested review points

| Area | Result | Notes |
|---|---|---|
| Auth / permission matrix | Static PASS | `deployment.execute_authorize` is required; critical/high mutation permissions are explicit; unknown role/action/resource denies. |
| AI_AGENT | Static PASS | Empty policy plus executor hard deny. |
| Approval / four-eyes | Static PASS | Expiry, rejected/missing, stale target, plan ID/SHA/action binding, and distinct approver checks are present. |
| Superseded plan | Static PASS | Superseding plans are marked and executor rechecks status and newer active plans. |
| Audit | Static PASS | Sanitized append-only model/trigger; no update/delete API found. |
| Deployment gate | Static PASS | Staging-only and fail-closed account/region/state/root checks; dangerous resource hints blocked. |
| SHA triple match | Static PASS | Stored artifact SHA == plan SHA == execution SHA, rechecked at authorize and prepare; approval SHA also checked. |
| TOCTOU | Static PASS by inspection | Artifact is reread and hashed during authorize and again during prepare. DB integration test was not runnable here. |
| Path safety | Static PASS | Relative allowlist and component symlink checks. |
| Arbitrary command / shell | Static PASS | The only subprocess call is inside the fixed read-only Terraform runner; no `os.system`, `eval`, `exec`, user command API, or `shell=True` exists. |
| AWS calls | PASS by static scope | No AWS client/import/call in executor or reviewed deployment services. |
| Production hard lock | Static PASS | Model constraints and executor/gate require staging. |

## Concurrency

`deployment_executions` has a partial unique index on `deployment_plan_id` for active states (`requested`, `validating`, `authorized`, `prepared`). This prevents two active executions for one plan at the database boundary; the existing collision test verifies the constraint blocks a duplicate. The request path also returns an already-visible active execution.

The existing collision path is fail-closed: a unique-constraint collision cannot create a second active execution and the transaction fails rather than proceeding. The focused test verifies the constraint. A dedicated two-session stress test was not added because the current database constraint test covers the security property without changing the implementation; future API ergonomics may translate this collision to the winning execution.

## Coverage and verification status

- Fresh final run: backend 82.55%; critical-service aggregate 90.86%; executor 76.44%; approvals 75.64%; deployment service 86.83%.
- The requested executor target of 85% was not reached in the available evidence. No meaningless tests were added.
- Ruff format check: PASS (107 files already formatted).
- Ruff lint: PASS.
- `compileall`: PASS.
- Bandit 1.8.3: PASS; High/Medium/Low = 0/0/0.
- Secret scan: PASS; no secret values are included in this report.
- pip-audit: PASS; `No known vulnerabilities found`.
- Focused security/gate/executor tests: 25 passed, 0 skipped, 29.38s.
- Backend full pytest with coverage: 220 passed, 0 skipped, 155.60s (runner wall-clock 165s), coverage threshold 80% passed.
- Migration chain: PASS in isolated PostgreSQL 16: upgrade head -> downgrade `ab12cd34ef56` -> upgrade head. Chain is `8d4f2a7c9b11 -> 9f1e4c2a7b30 -> ab12cd34ef56 -> cd34ef56ab78 -> head`.

## What is not implemented

Terraform CLI invocation, `terraform show`, plan/apply/destroy, AWS calls, state discovery, DNS/IAM/secrets/snapshot mutation, production execution, staging/production DB operations, and any automatic deployment side effect are not implemented. `executed_at` remains unset in this phase. The future apply boundary must use the exact approved materialized plan via fixed argv and repeat all authorization checks immediately before execution.

## Categorized diff summary

| Category | Changed files | Purpose / security property / review focus |
|---|---|---|
| AUTH | `app/auth/permissions.py`, `app/api/admin.py`, `app/api/automation.py`, `app/api/billing.py`, `app/api/projects.py`, `app/models/identity.py` | Permission matrix and enforcement; review unknown-role deny, project scope, last-owner protection, and actor type. |
| APPROVAL | `app/models/approval.py`, `app/services/approvals.py`, `app/api/approvals.py`, `app/api/schemas.py`, `migrations/versions/9f1e4c2a7b30_security_foundation.py` | Protected approval/four-eyes/expiry/checksum binding; review lifecycle reuse and cross-tenant checks. |
| AUDIT | `app/audit.py`, `app/models/identity.py`, `migrations/versions/9f1e4c2a7b30_security_foundation.py`, related API/service call sites | Sanitized result/reason/correlation metadata and append-only preservation; review no secret/plan-content logging. |
| DEPLOYMENT GATE | `app/models/deployment.py`, `app/services/deployment.py`, `app/api/deployment.py`, `migrations/versions/ab12cd34ef56_deployment_plan_gate.py`, `tests/test_deployment_gate.py`, `docs/staging_deployment_gate.md` | Staging hard lock, dangerous-resource blocks, SHA and approval binding; review hint-based detection limitations. |
| EXECUTOR | `app/models/execution.py`, `app/services/terraform_executor.py`, `migrations/versions/cd34ef56ab78_deployment_execution_preparation.py`, `tests/test_terraform_executor.py`, `docs/staging_terraform_executor.md`, `AGENTS.md` | Non-executing authorization/preparation boundary; review race collision handling, TOCTOU, symlink/root checks, and future CLI boundary. |
| DB MIGRATION | `migrations/versions/9f1e4c2a7b30_security_foundation.py`, `ab12cd34ef56_deployment_plan_gate.py`, `cd34ef56ab78_deployment_execution_preparation.py`, `tests/conftest.py` | Schema, FK, indexes, partial uniqueness, rollback order; live migration gate remains unverified here. |
| TEST | `tests/test_security_foundation.py`, `tests/test_deployment_gate.py`, `tests/test_terraform_executor.py`, `tests/conftest.py`, `quality-results/backend-coverage.json` | Security, gate, executor, collision, and coverage evidence; integration rerun is environment-blocked. |
| DOCS | `docs/enterprise_security_foundation.md`, `docs/staging_deployment_gate.md`, `docs/staging_terraform_executor.md`, `AGENTS.md`, this report | Human-review contract, prohibited operations, and future boundary. |

## Explicit non-actions

AWS changes: none. Production changes: none. Staging changes: none. Terraform init/plan/apply/destroy: none. Production/Staging DB operations: none. DNS changes: none. Git commit: NO. Git push: NO. Git merge: NO. Git stash/reset/restore/clean: NO.

## Step 3 — Isolated Terraform CLI verification

The read-only Terraform CLI boundary was added and verified using only a
provider-free local fixture. The runner resolves the fixed `terraform` binary,
uses argv lists with `shell=False`, validates the trusted workspace and saved
plan path, scrubs credential environment variables, bounds output, redacts
credential-shaped output, and exposes only `get_version()` and
`show_saved_plan_json()`. There is no generic command, apply, or destroy API.

- CI environment: Python 3.12.13 container, PostgreSQL 16 container, isolated
  ephemeral database and temporary fixture directory.
- Terraform: `/usr/bin/terraform`, v1.15.8; only `version` and local
  `show -json` were executed through the runner.
- Fixture creation: one provider-free `init -backend=false` and one local
  `plan -out`; no backend, provider, AWS, or remote state was used.
- Saved-plan verification: JSON parsing and minimal resource-change
  extraction passed; SHA-256 before/after equality passed; mutation,
  traversal, symlink, non-regular, invalid JSON, and non-zero-exit cases fail
  closed.
- Security integration: delete/destroy is blocked by the existing gate;
  production, AI_AGENT, and cross-tenant denial tests remain passing.
- Migration: existing chain round-trip passed in ephemeral PostgreSQL 16
  (`upgrade head` → `downgrade ab12cd34ef56` → `upgrade head`); no new schema
  migration was required.
- Focused security/gate/executor/Terraform suite: 39 passed, 0 skipped.
- Full backend pytest with coverage: 234 passed, 0 skipped, 168 seconds;
  overall coverage 82.55%, critical-service aggregate 90.86%, executor
  coverage 76.44%.
- Terraform runner coverage: 94% (14 passed, 0 skipped) in the same Python
  3.12.13 image; the first read-only-container attempt only exposed a
  non-code coverage-file permission issue and was rerun with coverage output
  in the container temporary directory.
- Ruff format/check: PASS. Bandit 1.8.3: PASS, High/Medium/Low = 0/0/2;
  the two low findings are Bandit's expected subprocess B404/B603 notices on
  the narrowly constrained runner call.
  Secret scan: PASS. pip-audit: PASS, no known vulnerabilities.
- Concurrency and idempotency remain protected by the existing partial unique
  index and collision handling; the regression suite passed without changing
  that security rule.

## Final Step 3 decision

**ENTERPRISE_PHASE2_TERRAFORM_CLI_VERIFICATION_READY**

No real Staging or Production Terraform root, state, AWS API, credential,
database, DNS, IAM, secrets, or deployment operation was used. Terraform
`apply` and `destroy` calls were zero. Actual saved-plan execution remains
blocked pending a separate design and approval.

## Future saved-plan execution boundary (design requirements only)

No execution code is included in this step. Before a future apply boundary is
approved, it must bind the approved `DeploymentPlan`, approval, and exact
saved-plan binary SHA; rehash the file immediately before launch; prohibit
re-plan and raw user arguments; and use fixed argv with the trusted binary.
It must revalidate state identity, AWS account, region, and Terraform root,
approval expiry, four-eyes approval, superseded-plan status, production hard
deny, and AI_AGENT deny. It must also enforce timeout, output redaction,
sanitized audit evidence, idempotency, concurrency locking, post-run evidence,
and fail-closed failure handling.

## Recommended next step

Human review of this read-only CLI boundary and its diff. A later step may
design an approved saved-plan execution boundary; it must preserve the fixed
argv, environment scrubbing, path/hash revalidation, staging-only gate, and
production hard lock. Actual apply remains a separate approval.
