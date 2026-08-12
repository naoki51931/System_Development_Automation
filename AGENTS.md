# AGENTS.md

Update this file whenever implementation changes so documentation and code stay aligned.

## Application structure

- `app/main.py`: FastAPI application factory and entry point; preserves `/docs` and mounts `/static`.
- `app/core/config.py`: Environment-backed application settings with safe local defaults.
- `app/db`: Lazy PostgreSQL engine and session infrastructure; application startup does not connect.
- `app/models`: Identity/RBAC plus tenant-scoped project, artifact, immutable version, review, AI-run, and approval-history models.
- `app/services/workflow.py`: Tenant-safe project/artifact operations and validated review/approval state transitions.
- `app/api/projects.py`: Authenticated minimal project, artifact, version, review, comment, submit, approve, and change-request APIs.
- `app/auth`: Cognito access-token verifier abstraction plus FastAPI authentication and tenant authorization dependencies.
- `app/seed.py`: Idempotent system-role seed command with no fixed role UUIDs.
- `docs/identity_access.md`: ER, Cognito validation, tenant boundary, deletion, audit, and RDS preflight design.
- `docs/project_artifact_review.md`: Project/artifact ER, workflow, constraints, API, migration, and security design.
- `schemas/openapi.yaml`: Versioned minimal API contract.
- `migrations`: Alembic baseline plus additive identity-access and project-artifact-review migrations; never apply to RDS without approval.
- `app/api/system.py`: Deployment-compatible `/health` API route.
- `app/web/routes.py`: Deployment-compatible server-rendered `/` route.
- `app/templates/index.html`: Japanese Jinja2 top-page template titled and branded `SystemNavigator AI`.
- `app/static/css/style.css`: Responsive, app-local CSS with no CDN or JavaScript dependency.
- `tests/test_app.py`: Endpoint and top-page content tests.
- `requirements.txt`: Pinned runtime and test dependencies.

## Local startup and tests

From `/home/ubuntu/ai-platform`:

```bash
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@LOCAL_HOST/LOCAL_DB pytest -q
APP_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DB alembic upgrade head --sql
APP_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DB python -m app.seed
```

`/health` must return `{"status":"ok"}` and Swagger UI remains at `/docs`.

## Docker build and verification

```bash
cd /home/ubuntu/ai-platform
docker build -t ai-platform:local .
docker rm -f ai-platform-local 2>/dev/null || true
docker run -d --name ai-platform-local -p 8000:8000 ai-platform:local
curl -i http://localhost:8000/
curl -i http://localhost:8000/health
curl -i http://localhost:8000/docs
docker logs ai-platform-local
docker rm -f ai-platform-local
```

Project/artifact migration revision `57d2abd856ae` adds eight tables and append-only/immutable triggers. Validate locally with downgrade to `0002_identity_access` followed by upgrade to `head`; never run the downgrade on RDS.

## ECS deployment

ECR is `557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod`. Build and push the tag selected by `container_image_tag` in `environment/terraform.tfvars` (currently `v4`), then deploy through a reviewed saved Terraform plan.

```bash
aws ecr get-login-password --region eu-west-2 | docker login --username AWS --password-stdin 557604519341.dkr.ecr.eu-west-2.amazonaws.com
docker tag ai-platform:local 557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod:v4
docker push 557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod:v4
cd /home/ubuntu/ai-platform/environment
terraform fmt -recursive
terraform init -backend-config=backend.hcl
terraform validate
terraform plan -out=app-v4.tfplan
terraform apply app-v4.tfplan
```

Before apply, allow replacement of only the ECS task definition when it creates a new revision and updates the ECS service. Stop if the plan destroys RDS, S3, VPC, ALB, ECS cluster, Terraform state-related resources, or any other persistent infrastructure. Never commit `terraform.tfvars`, `backend.hcl`, saved plans, state, or secrets. After apply, wait for desired 1, running 1, pending 0, then verify `/`, `/health`, and `/docs` through the ALB.


## Integration baseline

- Authentication target is AWS Cognito access tokens; verify signature, issuer, expiry, subject, token_use, and client_id or audience. Do not create or change Cognito resources without approval.
- Users are global by unique lowercase email and unique Cognito sub; organization roles belong to memberships, not directly to users.
- Authorization order is JWT, user status, membership, membership role, resource organization, then operation.
- RDS connections and migrations require explicit approval; local PostgreSQL is the only allowed migration target during development.

- Baseline commit before design-package integration: `def4176`.
- Preserve port `8000` and the existing ALB/ECS `/health` response during incremental integration.
- Add new APIs under `/api/v1`; do not move or replace the public root page in the backend integration phase.
- Keep `*-plan.txt`, saved Terraform plans, state, real tfvars, backend configuration, and secrets out of Git.
- Do not run Terraform apply/destroy, change AWS resources, push images, or send external data until the exact action and impact have been reviewed and approved.

## AI/storage workflow phase

- `app/models/automation.py`: tenant-scoped AI settings, bounded workflow jobs, and upload intents.
- `app/services/automation.py`: setting resolution, Decimal billing snapshots, uploads, audited comment transitions, optimistic locking, and bounded mock revision.
- `app/services/ai_providers.py`: AIProvider, local MockAIProvider, and network-disabled OpenAI/Anthropic stubs.
- `app/services/storage.py`: ArtifactStorage, validated local storage, and network-disabled S3 stub.
- `app/api/automation.py`: AI setting, upload intent/completion/download, and review comment action APIs.
- `docs/ai_storage_workflow.md`: storage key, billing, transition, retry, and concurrency contract.
- Migration `0003_ai_storage_workflow` is additive. Generate SQL only with a local PostgreSQL URL; do not connect to RDS.
- Tests use local PostgreSQL, local filesystem/MinIO, and MockAIProvider only. Never enable external AI or AWS S3 calls. Future credentials come from Secrets Manager and are never persisted.

## Estimate/contract/payment phase

- `app/models/billing.py`: tenant estimates/items, immutable pricing snapshots, contracts, payment metadata/intents/events, subscriptions/invoices, maintenance plans/contracts/events, and deletion requests.
- `app/services/billing.py`: Decimal totals and tax, AI/artifact lines, contract acceptance, idempotent payment, UTC delinquency, recovery, two-person deletion approval, and webhook hashing.
- `app/services/payment_providers.py`: PaymentProvider, deterministic local MockPaymentProvider, and network-disabled Stripe stub.
- `app/api/billing.py`: authenticated estimate, contract, payment, maintenance, and mock webhook APIs.
- `app/seed.py`: idempotent light, standard, and premium system maintenance plans.
- `docs/estimate_contract_payment.md`: pricing, lifecycle, card-data prohibition, idempotency, and no-destroy contract.
- Migration `215db73ed802` is additive; its SQL is generated offline. Use only local PostgreSQL for validation.
- Never call Stripe, expose Stripe webhooks, accept card numbers/CVC, connect to Secrets Manager/RDS/AWS, run Terraform, send billing email, or execute deletion in this phase.

## Notifications/documents/chat phase

- `app/models/communications.py`: preferences, notifications/deliveries, versioned templates/messages, generation jobs, chat, change impacts, and local outbox.
- `app/services/communication_providers.py`: Mock notification/email providers and network-disabled SES/SMTP stubs.
- `app/services/communications.py`: quiet-hour scheduling, secret/XSS sanitization, allowlisted rendering, local PDF/artifact generation, chat authorization, MockAI analysis, and idempotent events.
- `app/api/communications.py`: authenticated notification, document, email, chat, attachment, and change-request APIs.
- `app/seed.py`: approved system-default email template versions in addition to roles and maintenance plans.
- `docs/notifications_documents_chat.md`: provider boundaries, templates, PDF, artifact relationships, chat/change flow, outbox, and security.
- Migration `d8685773bc4a` is additive and has offline SQL. Validate only with local PostgreSQL.
- Use only LocalArtifactStorage, MockEmailProvider, MockNotificationProvider, and MockAIProvider. Never connect to SES/SMTP/S3/external AI/RDS/AWS or expose public WebSockets.
- Future SES, S3, and provider credentials must come from Secrets Manager at runtime; never persist or log them.

## Web portal and local worker phase

- `frontend/` is the separate Next.js/TypeScript application. It uses only local CSS, a shared cookie/CSRF API client, accessible responsive shell, role-oriented portal/admin screens, and no external UI service.
- `app/api/local_auth.py` provides development-only test-user login with a short-lived HttpOnly signed cookie. Tokens contain only the immutable user subject; organization and roles are always loaded from PostgreSQL. `APP_ENV=production` or `APP_LOCAL_AUTH_ENABLED=false` disables LocalAuth. Cognito remains a network-disabled stub.
- `app/api/pagination.py` signs `created_at + id` cursors with HMAC, rejects tampering, caps pages at 100, and always applies tenant filters before cursors.
- `app/workers/` claims Outbox jobs with `FOR UPDATE SKIP LOCKED`, worker identity, heartbeat, expiring lease, bounded exponential retry, idempotency constraints, and dead letter state. Providers remain local mocks.
- Migration `6b1e4c9f2a10` only adds Outbox lease/retry columns and an index; offline SQL is committed. Never apply it to RDS in this phase.
- `compose.yaml` starts local PostgreSQL, backend, frontend, and worker. It contains local-only credentials and never enables Cognito, Stripe, SES, S3, external AI, AWS, or public deployment.
- Run `docker compose up --build`, `docker compose run --rm backend python -m pytest -q`, and `docker compose run --rm frontend npm test`. LocalAuth must never be enabled in a production environment.

## Staging readiness quality gate

- `schemas/openapi.yaml` is generated from `app.main:app` by `scripts/export_openapi.py`; do not hand-edit it. `frontend/lib/generated/api.ts` is generated by `npm run openapi:generate`; `npm run openapi:check` fails on drift.
- Portal screens use the shared no-store cookie/CSRF/timeout/error wrapper and clear session-scoped organization/project state when the tenant changes.
- `app/quality` contains synthetic E2E and scalable performance seeds. `performance/locustfile.py` is local-only; results and EXPLAIN JSON live in `quality-results/` and are not production SLA evidence.
- `APP_FAULT_INJECTION` enables named Mock failures only outside production. Never enable it in staging or production.
- `.github/workflows/quality-gate.yml` is an unpushed proposal with no AWS credentials. Coverage thresholds intentionally block staging while current measured coverage remains below target.
- Staging remains prohibited until `docs/staging_deployment_checklist.md` approvals are complete. This phase did not run Terraform, connect AWS/RDS/providers, push GitHub/ECR, or deploy.

## Quality-gate remediation baseline

- Docker images use multi-stage slim/alpine builds, explicit COPY allowlists, cache-free dependency installation, non-root runtime users, standalone Next output, and health checks. Python build/quality stages pin pip 26.1.2; the final runtime stage removes pip and does not contain pip-audit or other test/security tools.
- Docker build contexts exclude Python bytecode recursively (`**/__pycache__`, `**/*.pyc`) so host-version artifacts cannot enter runtime layers, including with the legacy Docker builder.
- The staging backend remains Python 3.12.13 but uses a digest-pinned official Alpine 3.24 base because Debian's essential `perl-base` retained CRITICAL/HIGH findings; Alpine compatibility must stay covered by the full backend and container runtime gates.
- Revision `7c2f9a1e4d30` adds tenant/cursor and worker-claim indexes only. Its review SQL is `migrations/offline/7c2f9a1e4d30_quality_gate_indexes.sql`; do not apply it outside local PostgreSQL in this phase.
- `DOCUMENT_RENDER_FAILURE` is injected before rendering or storage. Tests require rollback, bounded retry/dead letter, sanitized errors and idempotent regeneration. PostgreSQL lock-timeout/deadlock SQLSTATEs are retryable without exposing SQL.
- Browser binaries are cached at `/home/ubuntu/.cache/ms-playwright`. All three browser projects execute role, tenant, error-contract, workflow and 12-route axe checks without rule exclusions.
- Coverage gates are backend 80%, important-service aggregate 90%, and frontend major-feature branches/functions/statements/lines 70%. Generated OpenAPI, configuration and type-only files are excluded from frontend coverage because they contain no executable user decisions.
- `quality-results/quality-gate-summary.md` is authoritative. Any FAIL or BLOCKED means staging is `NOT_READY`; never weaken a threshold to obtain READY.
- `scripts/check_service_coverage.py` owns the fixed critical-service list; the 2026-08-05 aggregate is 86.12%, below 90%.
- The 2026-08-05 audit confirmed the 50-user/60-second endpoint performance gate passes, but Compose worker health and real handler dispatch/resume fail; `npm audit` is DNS-blocked and the image build reports two moderate findings.
- `APP_PERFORMANCE_TIMING=true` is local-performance-only and emits sanitized durations/counts without SQL or secrets; production defaults to disabled.

## 2026-08-05 worker remediation

- Worker registry types are `outbox`, `notification`, `email`, `document`, `ai_workflow`, `maintenance`, `estimate_expiration`, and `notification_expiration`; unknown types dead-letter.
- Claims commit before handlers. A separate DB session renews the 60-second lease every 20 seconds; completion is an owner/lease CAS. Lease or DB loss prevents completion.
- Worker health uses an atomic local status file plus PID, poll freshness, dead-letter count, and PostgreSQL checks. Compose requires all four services healthy.
- Frontend production uses `.next/standalone` with `node server.js`, non-root runtime, and `HOSTNAME=0.0.0.0`; development remains `next dev`.
- E2E setup is `APP_ENABLE_E2E_SEED=true scripts/compose-e2e-setup.sh`; it refuses production.
- PostCSS is overridden to 8.5.23 for GHSA-fxqj-rqcc-2cmp. `npm audit --omit=dev` reports zero vulnerabilities.
- Revision `6b1e4c9f2a10` replaces `ck_outbox_events_status` with DROP/ADD after row preflight. It takes ACCESS EXCLUSIVE locks and is not drop-free; downgrade is destructive/local-only.
- Staging remains `NOT_READY`: backend overall coverage is 79.86%, critical-service coverage is 86.02%, and safe automatic resume of legacy partial document/AI workflow rows remains incomplete.

## 2026-08-06 resumable workflow completion

- Revision `8d4f2a7c9b11` adds `workflow_job_inputs`, `workflow_job_steps`, deterministic job keys, parent/requeue links, `resume_block_reason`, and `resume_blocked_at`. Snapshots use schema version `1`; PostgreSQL rejects snapshot UPDATE/DELETE and changes to completed steps.
- Document resume reuses the frozen template/input, deterministic artifact/version ID and storage key, and verifies render/storage SHA-256 before publication. AI resume uses frozen source/comment/settings hashes and deterministic run/version/review/billing identities.
- Legacy processing/retry jobs without a snapshot fail closed with `RESUME_SNAPSHOT_MISSING` and require administrator review/requeue. Lease loss prevents the old worker from committing.
- Final local results: Backend 125 passed, overall 83.09%, critical services 90.86%; Frontend 34 passed; Chromium/Firefox/WebKit 23 passed each and axe critical/serious 0. Local implementation is READY; staging remains separately approval-gated.

## Staging Terraform separation

- `/environment` remains the unchanged production root with state key `cloud-a/prod/terraform.tfstate` and prefix `ai-platform-prod`; do not move it or migrate its state.
- `/environment/staging` is the staging-only root with state key `system-navigator/staging/terraform.tfstate`, prefix `system-navigator-staging`, and additive modules under `modules/staging_*`.
- Commit only `backend.hcl.example` and `terraform.tfvars.example`. Real backend files, tfvars, state, plans, ARNs, domains, notification addresses, and secret values stay untracked.
- Staging images must use a Git SHA or image digest; `latest` is rejected. `APP_ENV=staging` and `APP_LOCAL_AUTH_ENABLED=false` are fixed in ECS, and application startup refuses LocalAuth in staging/production.
- Mock AI/payment/email providers are explicit staging flags. Cognito, Stripe test mode, SES Sandbox, HTTPS/DNS, and secret values remain disabled/unpopulated until separately approved.
- Staging owns its RDS, artifact bucket, ECS cluster/services/tasks, ALB/target groups, logs, secrets, IAM roles, monitoring, and migration-only task. Never share production RDS, S3, secrets, identity, services, DNS, or provider configuration.
- Staging RDS is the low-cost profile: `db.t4g.small`, Single-AZ, 20 GB gp3, and three-day backup retention, while remaining private, encrypted, and deletion-protected. The high-availability Multi-AZ profile is production-only; do not change production modules, tfvars, or backend when tuning staging.
- Main staging bootstrap defaults `enable_runtime_services=false`: create infrastructure and all task definitions first, but no backend/worker/frontend services or runtime alarms. Populate the application DB Secret outside Terraform, confirm RDS backup/PITR, run the separately approved one-off migration to exit 0/Alembic head, then review a new `enable_runtime_services=true` plan. Frontend container and ALB health use `/login`; backend remains `/health`.
- Staging Cloud Map services intentionally omit an empty `health_check_custom_config` block: AWS/provider refresh does not retain it and would otherwise propose ForceNew replacement. Do not mask that drift with `ignore_changes`. The reconciled main state is no-op, but Secret registration and migration remain blocked until RDS exposes a non-null earliest PITR timestamp; take a separately approved manual snapshot before migration.
- Run `terraform init -backend=false` and `terraform validate` separately in `/environment` and `/environment/staging`. A plan, apply, migration, AWS discovery/change, provider connection, or push always requires the documented human approval.
- Staging now has explicit `staging_mode = "idle" | "active"`. IDLE retains state, VPC primitives, S3 Gateway Endpoint, artifact S3, application Secret container, IAM and 14-day log groups, while omitting RDS, ALB, Interface Endpoints, ECS/Cloud Map/task definitions and infrastructure alarms. Production has no mode variable and must remain unchanged.
- ACTIVE staging is fail-closed behind `allow_staging_reactivation=true`; changing an ignored local tfvars file to `staging_mode="active"` otherwise fails planning before it can propose recreating the costly RDS, ALB, Interface Endpoints, ECS/Cloud Map and alarms. This gate permits planning only and never replaces saved-plan review or apply approval.
- Never apply the review-only `staging-idle.tfplan`. Long-idle RDS removal requires an available manual snapshot, a tested restore, a separate reviewed change disabling RDS deletion protection, zero services/tasks/connections, the guarded `scripts/staging_idle_apply.sh` preflight, and final human approval. The script creates an approved plan but never applies it.
- Staging database protection/removal phases are gated by `allow_database_deletion=false` by default, the existing removal approval, and an AWS-verified available manual snapshot. First review the ACTIVE protection-only plan, then require the flags again for a fresh IDLE removal plan; never reuse an old plan.
- ACTIVE restore accepts an ignored `db_snapshot_identifier` only with `restore_db_from_snapshot=true`; restore RDS first with runtime services disabled, update the persistent application DB Secret outside Terraform, confirm PITR/schema, migrate with approval, and only then enable services.

## Staging pre-plan resource preparation

- `environment/staging-prerequisites` owns the two immutable ECR repositories, GitHub staging deploy role/policy, staging SNS email subscription, and 150 USD Budget in state `system-navigator/staging/prerequisites.tfstate`. AWS Budgets for this account accepts USD only; the rejected former setting was 100 GBP. Custom-domain ACM and DNS validation are conditional and disabled until a new domain is explicitly approved. It owns no VPC, RDS, ECS, ALB, S3, or Secrets.
- Backend, worker, and migration share one reviewed application digest with separate commands/roles. Main staging accepts only account/region ECR URIs pinned with `@sha256`; local image IDs are not registry digests.
- GitHub trust is exactly the `staging` Environment. Enforce approved branches in GitHub Environment protection; never broaden trust to `repo:...:*`.
- Initial networking is dedicated `10.30.0.0/16`, isolated DB subnets, no NAT, and explicit ECR/S3/Logs/Monitoring/Secrets/STS/KMS endpoints. Review egress before enabling non-mock providers.
- No SystemNavigator AI resource may use `true-camera-test.com`. Until a replacement domain is approved, custom domains, ACM, Route53 aliases, HTTPS listeners, Cognito, Stripe, real authentication, and sensitive data are disabled; temporary staging checks use the ALB HTTP DNS name only. Main staging receives SNS topic and deploy-role ARNs explicitly, never through a reverse dependency. Alert email and Budget inputs live only in ignored prerequisite tfvars; SNS email requires confirmation.
- Initially create only the database Secret container. Optional containers appear only with their providers, and Terraform never manages Secret values.
- Production has a reviewed `production_capacity_profile="low-traffic"` for 100 RPM steady and 600 RPM short burst: a separate 256 CPU/512 MiB task-definition family, desired/min 1 and max 2 target tracking, and `db.t4g.small` while retaining Multi-AZ, 50 GiB storage, ALB and NAT. The known-good 512/1024 task definition remains registered for rollback. Never apply the saved plan without a fresh Production manual snapshot/PITR check and separate approval.
- Production monitoring is isolated on the planned `ai-platform-prod-alerts` topic with 13 ALB/ECS/RDS alarms; it never uses staging SNS. The approved recipient is `info@nagi-neco.com`; Terraform disables automatic confirmation, so a human must confirm the AWS email subscription after an approved apply.
- Production PITR approval is fail-closed through `scripts/production_pitr_gate.py`, which uses only RDS `describe-*` APIs. A null `DBInstance.EarliestRestorableTime` is recorded as `PITR_API_FIELD_WARNING` and does not block by itself; the matching active automated-backup record must still have positive matching retention, matching `DbiResourceId`, a complete ordered `RestoreWindow`, an available encrypted latest automated snapshot, no recent backup failure, and an available encrypted pre-change manual snapshot.
- The saved plan `production-100rpm-remediated-final.tfplan` with SHA-256 `d6f094ded385f70628f9e0840e86c051fc2308d78a6afc313d5aafe32e8a5df0` is **STALE / INVALID** and must not be applied. Only a fresh plan from `cloud-a/prod/terraform.tfstate`, with zero replacement and destruction after review, can enter human apply approval.
- The local prerequisite-root gate is `READY_FOR_STAGING_PREREQUISITES_PLAN_APPROVAL` only. This permits humans to approve a prerequisites plan, not apply. No AWS change, apply, ECR/GitHub push, RDS connection, or migration is implied.
- The approved staging operations recipient is `info@nagi-neco.com`, supplied only through ignored `environment/staging-prerequisites/terraform.tfvars`. CloudWatch alarms publish to the prerequisite `system-navigator-staging-alerts`; its email subscription remains `PendingConfirmation` until a human confirms it. AWS Budgets sends 50/80/100% actual and 100% forecast notifications directly to the same address for the 150 USD monthly budget. Never auto-confirm, send application mail to this address, build SES inbound/MX/S3 inbox infrastructure, or alter `nagi-neco.com` DNS/mail service.
