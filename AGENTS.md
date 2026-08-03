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
