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

See `docs/staging_readiness.md`, `docs/staging_deployment_checklist.md`, `docs/db_performance_quality.md`, and `quality-results/summary.md`. The quality gate currently blocks staging because coverage targets and full browser/Compose verification are not yet satisfied.
# Quality gate remediation

The reproducible local gate uses `docker compose down -v --remove-orphans`, `docker compose build --no-cache`, `docker compose up -d`, backend/frontend tests, and `cd frontend && npx playwright test`. Browser downloads are cached in `/home/ubuntu/.cache/ms-playwright`. Performance evidence uses 50 Locust users for at least 60 seconds and distinguishes cold and warm runs. See `quality-results/quality-gate-summary.md`; the current decision is **NOT_READY** because fixed important-service coverage and normal-API p95 gates remain unmet.
