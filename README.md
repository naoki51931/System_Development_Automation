# SystemNavigator AI

FastAPI application currently deployed on AWS ECS. The public `/`, `/health`, and `/docs` compatibility contracts remain unchanged while the design package is integrated incrementally.

## Local verification

Dependencies are pinned in `requirements.txt`. The identity integration tests require PostgreSQL and use only a local test database. Do not point test commands at RDS.

```bash
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@LOCAL_HOST/LOCAL_DB pytest -q
APP_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@LOCAL_HOST/LOCAL_DB alembic upgrade head --sql
```

Identity and Cognito tenant boundaries are documented in `docs/identity_access.md`. Project, artifact, immutable version, AI/human review, approval workflow, additive migration, and RDS preflight requirements are documented in `docs/project_artifact_review.md`. The minimal API contract is in `schemas/openapi.yaml`.

The project workflow is `draft -> ai_reviewing -> human_reviewing -> approved`, with change requests creating a new immutable artifact version. All tenant resources are checked against authenticated organization membership; request organization IDs are never trusted alone.

Terraform apply/destroy, AWS resource changes, ECR pushes, ECS deployments, RDS connections, and RDS migrations require explicit review and approval.

## Isolated staging infrastructure

The existing production Terraform root remains at `environment/` with its existing `cloud-a/prod/terraform.tfstate` state key. The additive staging root is `environment/staging/`, uses `system-navigator/staging/terraform.tfstate`, and creates only `system-navigator-staging-*` resources. See `docs/staging_terraform_layout.md` before any cloud work.

Static checks only:

```bash
terraform fmt -recursive
terraform -chdir=environment init -backend=false
terraform -chdir=environment validate
terraform -chdir=environment/staging init -backend=false
terraform -chdir=environment/staging validate
pytest -q tests/test_staging_terraform.py tests/test_web_workers.py
```

Do not copy example placeholders into an approved plan without replacing and reviewing them. Image references require a Git SHA or digest, LocalAuth is rejected in staging/production, and real `backend.hcl`, `terraform.tfvars`, secret values, account-specific ARNs, domains, and alert email addresses must not be committed. `plan`, `apply`, secret population, migration, provider connections, and AWS discovery remain separate approval points.

Staging RDS is intentionally low-cost: `db.t4g.small`, Single-AZ, 20 GB gp3, and three-day backup retention. It remains private, encrypted, and deletion-protected. Only production uses the high-availability Multi-AZ RDS configuration; production Terraform and backend configuration are separate and unchanged.

Pre-plan preparation uses `environment/staging-prerequisites` for two ECR repositories, the staging-only GitHub OIDC role, SNS email subscription, and the 150 USD Budget. AWS Budgets rejected the former 100 GBP setting because this account accepts USD only. `true-camera-test.com` is not used. Custom domain, ACM, Route53 alias and HTTPS remain disabled until a new domain is approved. Main staging temporarily exposes only its ALB HTTP DNS name and accepts only full `repository@sha256:...` image URIs. The dependency is prerequisites → staging only.

The staging notification recipient remains `info@nagi-neco.com` and Budget is 150 USD; real values live only in ignored prerequisite tfvars. CloudWatch alarms use the prerequisite SNS topic, while AWS Budgets notifies the address directly. SNS confirmation is manual. ALB HTTP access is temporary, non-production, non-customer, and must not carry credentials, payment flows, real authentication, or sensitive data.

## Local AI, storage, review, and concurrency phase

AI settings resolve project -> organization -> safe system defaults. Billing uses Decimal/NUMERIC(18,8), rounds every non-zero partial minute up, and stores rate snapshots on each AI run. Artifact files use server-generated tenant keys and are verified by MIME type, size, and SHA-256 before immutable version registration. Review comments use audited state transitions, and SQLAlchemy version columns return conflicts instead of overwriting concurrent updates.

See `docs/ai_storage_workflow.md` for APIs, validation, mock automatic revision, retry escalation, and locking. This phase never calls OpenAI, Anthropic, AWS S3, RDS, Terraform, ECR, ECS, or a public environment. External provider and S3 classes are disabled stubs. API keys are never stored; future runtime credentials will come from AWS Secrets Manager.

## Estimate, contract, payment, and maintenance billing

Server-side Decimal pricing now covers AI runtime, immutable artifact-value snapshots, manual work, discounts, and isolated tax calculation. Approved unexpired estimates become versioned contracts; customer and provider acceptance activate them. Idempotent MockPaymentProvider intents support succeeded, failed, and processing outcomes, and only success advances a project to requirements.

Maintenance billing models 7/30/60/90-day delinquency boundaries. Day 90 creates a two-approver resource deletion request only—no AWS deletion or Terraform destroy exists. Card number, CVC, payment secrets, and raw webhook payloads are never stored. Stripe API and public Stripe webhooks remain disabled. See `docs/estimate_contract_payment.md`.

## Local notifications, documents, and project chat

Tenant notification preferences now support IANA timezones, quiet hours, digests, critical-event overrides, deduplicated deliveries, and audited critical alerts. Email uses allowlisted templates and one-recipient snapshots through MockEmailProvider only; SES/SMTP remain disabled.

Approved estimate, contract, and basic-design data can produce local HTML, Markdown, or PDF artifact versions with SHA-256 and idempotent jobs. Project chat uses membership checks, safe plain text, logical deletion, verified artifact attachments, explicit AI identity, and MockAI-assisted change impacts that always await human/customer approval. A local outbox prevents duplicate event, notification, and email processing. See `docs/notifications_documents_chat.md`.

## 管理画面・顧客ポータル・ローカルワーカー

Next.js UI is now a separate process under `frontend/`, branded **SystemNavigator AI** / 「AIと人が、システム開発を完成までナビゲート。」. Customer, sales/PM, reviewer, developer, organization administrator, and system operations views share an accessible responsive shell. API values are authoritative—especially estimate/payment totals—and optimistic updates never overwrite a 409 conflict.

```bash
docker compose up --build
docker compose run --rm backend python -m pytest -q
docker compose run --rm frontend npm test
```

The local stack contains PostgreSQL, FastAPI, Next.js, and a polling worker. LocalAuth uses a short-lived HttpOnly cookie plus CSRF token and is rejected in production. Cognito, Stripe, SES, S3, external AI, RDS, AWS and public environments remain disconnected. See `docs/web_portal_and_workers.md` and `frontend/README.md`.

## Staging-readiness quality gate

The portal now reads dashboard, project, estimate, contract, Mock payment, artifact/version, review/comment, chat/change-request, notification, AI-setting, maintenance, organization-user, audit, and dead-letter data from FastAPI. OpenAPI is exported from the app and TypeScript types are generated under `frontend/lib/generated`.

```bash
python scripts/export_openapi.py
cd frontend && npm run openapi:generate && npm run openapi:check
cd .. && ./scripts/quality_gate.sh
QUALITY_SCALE=0.01 python -m app.quality.seed_performance
locust -f performance/locustfile.py --headless -u 50 -r 10 -t 20s --host http://localhost:8000
```

See `docs/staging_readiness.md`, `docs/staging_deployment_checklist.md`, and
`quality-results/quality-gate-summary.md`. Run
`python scripts/check_service_coverage.py quality-results/backend-coverage.json`
after coverage. The 2026-08-05 audit gate is **NOT_READY**: critical services are
86.12% (required 90%), the Compose worker has no healthcheck, and its runner does
not dispatch or resume real handlers. The formal 50-user/60-second endpoint gate
now passes (normal project detail p95 490 ms; list worst p95 540 ms; 0% errors),
but `npm audit` remains DNS-blocked and the image build reported two moderate npm
findings. Local timing headers require `APP_PERFORMANCE_TIMING=true` and stay
disabled in production.
# Quality gate remediation

The reproducible local gate uses `docker compose down -v --remove-orphans`, `docker compose build --no-cache`, `docker compose up -d`, backend/frontend tests, and `cd frontend && npx playwright test`. Browser downloads are cached in `/home/ubuntu/.cache/ms-playwright`. For a seeded Compose E2E run use `APP_ENABLE_E2E_SEED=true scripts/compose-e2e-setup.sh`; production is rejected. The production frontend is a non-root Next standalone image launched with `node server.js`. See `quality-results/quality-gate-summary.md`; the current decision is **NOT_READY** because backend coverage and safe document/AI workflow resume remain mandatory failures.

## Resumable Document and AI workflows (2026-08-06)

Migration `8d4f2a7c9b11` introduces immutable schema-version `1` `workflow_job_inputs` snapshots and durable `workflow_job_steps`. Document generation resumes with a deterministic artifact version/storage key and verifies render/storage SHA-256. AI revision resumes from frozen source/comment/settings hashes and deterministic AI run, artifact version, review, and billing identities, preventing duplicate versions, reviews, or AI cost.

Snapshots and completed steps cannot be changed or deleted. A partial job without a snapshot is never reconstructed from current template, AI setting, comments, pricing, actor, or artifact; it records `RESUME_SNAPSHOT_MISSING`, `resume_block_reason`, and `resume_blocked_at` for administrator review/requeue. Worker owner/lease CAS prevents a lease-lost worker from committing.

Final local evidence: Backend 125/125, overall 83.09%, critical services 90.86%, Frontend 34/34, and Chromium/Firefox/WebKit 23/23 each with axe critical/serious 0. The local software gate is READY; staging/cloud execution still requires checklist approvals.
