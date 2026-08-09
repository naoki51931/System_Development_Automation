# SystemNavigator AI staging readiness

## Purpose and production differences

Staging validates deployment, identity, provider boundaries, migration, tenant isolation, observability, and rollback before production. It uses synthetic data only, separate accounts/resources/secrets, lower scaling, strict cost budgets, Cognito test users, Stripe test mode, and either SES Sandbox or Mailpit. Production customer data and production credentials are forbidden.

## Proposed services and approval points

A dedicated VPC/ALB service set would contain ECS backend/frontend/worker, ECR images pinned by digest, RDS PostgreSQL, a versioned S3 staging bucket, Secrets Manager, and CloudWatch logs/metrics/alarms. Custom domain, ACM, Route53, HTTPS, Cognito, Stripe, and SES are disabled. External AI stays Stub by default; any provider connection requires separate approval.

Approval is required before: Terraform plan, any destroy/replacement, secret registration, RDS access/migration, ECR push, ECS deployment, DNS/HTTPS change, Cognito/Stripe/S3/SES connection, external AI enabling, or data reset. Set AWS Budgets alerts and service quotas before creation.

The code boundary now exists without changing AWS: production stays in `environment/` with key `cloud-a/prod/terraform.tfstate`; staging is `environment/staging/` with key `system-navigator/staging/terraform.tfstate`. Staging defaults to a dedicated VPC but can consume an explicitly supplied existing VPC plus two public and two private subnets. The modes are mutually exclusive. A dedicated VPC provides the strongest routing and security boundary; existing-VPC subnets reduce NAT cost but increase shared blast radius and require a separate network review.

All staging resource names contain `system-navigator-staging`. Images use immutable Git SHA `57109fa` by default or a digest, never `latest`. Mock AI/payment/email are visibly enabled by environment variables; Cognito, Stripe, and SES are disabled until approved. Stripe is test-only and rejects live mode; SES requires Sandbox. The application refuses to start with LocalAuth enabled in staging or production.

## Migration, seed and deploy order

1. Freeze a tested Git commit and immutable image digests.
2. Review offline migration SQL, locks and rollback classification; snapshot RDS.
3. Review a saved Terraform plan, with explicit destroy/replacement inventory.
4. Register staging-only Secrets Manager values and disable LocalAuth (`APP_ENV=staging`, `APP_LOCAL_AUTH_ENABLED=false`).
5. Push reviewed images, apply only the approved saved plan, and run one migration-only ECS task.
6. Run idempotent system/reference seed only; load synthetic test data separately.
7. deploy backend, worker, then frontend; verify ALB HTTP health and CloudWatch. HTTP is temporary and forbidden for production/customer/sensitive/real-authentication use.
8. Execute tenant, billing-test, S3, document, email-sandbox, worker and alarm smoke tests.

The migration task runs `alembic upgrade head` independently; backend startup never runs migration. Required order is verified snapshot, migration task, exit code 0, Alembic head verification, backend update, then worker update. Any migration failure stops service updates.

S3 uses blocked public access, encryption, tenant-prefixed keys, CORS limited to the staging origin, lifecycle rules, and versioning. Stripe uses test keys/webhooks only. Cognito uses a separate pool and callback URLs. SES Sandbox restricts verified recipients; Mailpit remains the local alternative.

## Rollback

Application rollback selects the previous ECS task definitions and immutable image digests, then stops new workers if schema compatibility is uncertain. Prefer a forward fix for additive migrations. Downgrade is allowed only when offline SQL review proves it non-destructive and no newer data depends on it. Otherwise restore an RDS snapshot into a new instance and switch only after validation.

Preserve S3 versions and audit logs. Roll back Secrets Manager by version stage, restore Cognito configuration from reviewed export, disable Stripe webhooks before reverting consumers, stop workers before DB restoration, and switch DNS only after old-target health verification. Never erase audit evidence during reset or rollback.

The staging RDS uses an intentionally low-cost `db.t4g.small`, Single-AZ configuration with 20 GB gp3 storage and three-day backup retention. It remains private, encrypted, and deletion-protected. The high-availability Multi-AZ RDS configuration is production-only. AWS manages the staging master password in Secrets Manager. Application and migration identities must be provisioned after approval: migration owns DDL; application owns only runtime DML. Terraform creates additional empty secret containers and IAM references only; values are inserted through a separately approved, audited procedure.

## Final quality-gate recheck (2026-08-05)

The remediation decision is **NOT_READY**. Ruff is clean, but backend coverage is
79.86% (required 80%) and critical-service coverage is 86.02% (required 90%). The formal
50-user/60-second endpoint gate now passes (normal project detail p95 490 ms and
list worst p95 540 ms, 0% errors). Compose worker health and real handler
dispatch and heartbeat are implemented and all four Compose services are healthy.
Safe automatic resume of legacy partial document/AI workflow rows remains incomplete.
The two moderate findings were the same PostCSS advisory and are fixed by 8.5.23;
the reproducible npm audit now reports zero vulnerabilities.

## Data, observability and cost

Use generated organizations/users/projects only, tagged with expiry. Reset by approved staging-specific procedure after exporting audit evidence. CloudWatch covers 5xx, latency, task restarts, worker lease age, retry/dead-letter count, RDS CPU/connections/storage and ALB health. Define monthly cost ceiling, daily anomaly alert, NAT/log retention limits and manual approval for scale increases.

Chargeable components are NAT Gateway/EIP, ALB, ECS Fargate, RDS, S3 requests/storage, Secrets Manager, CloudWatch logs/alarms, SNS, AWS Budgets, and optionally Route53/ACM data transfer. Cost controls are Single-AZ RDS, small tasks, desired count one, short logs, lifecycle rules, and approved off-hours scheduling. Replacing NAT with reviewed VPC endpoints can reduce recurring cost without making tasks public; WAF can remain an explicit later option, not a reason to relax ALB or TLS controls.

## Read-only AWS discovery (2026-08-06)

Account, region, state backend/KMS, production inventory, non-colliding staging VPC/RDS/S3 candidates, OIDC provider, and base RDS orderability are confirmed. The gate remains **NOT_READY_FOR_TERRAFORM_PLAN_REVIEW** because staging ECR repositories and the `57109fa` image/digest do not exist, the staging-only deploy role and Secret containers are missing, ACM is absent, notification/Budget inputs are absent, and quota verification is incomplete. See `quality-results/aws-read-only-discovery-2026-08-06.md`. No plan or AWS mutation was performed.

Pre-plan remediation uses a distinct prerequisites state for ECR, strict GitHub Environment trust, SNS and Budget. `true-camera-test.com` is rejected and no replacement domain is selected; conditional ACM/DNS resources remain disabled. Main staging receives outputs explicitly and retains VPC/storage/Secrets/RDS/ECS/ALB and alarms. No reverse state reference or circular dependency exists.

The resumed local verification produced four Terraform validate passes, 16 Terraform safety tests (one provider-schema skip), 140 backend tests, 83.09% overall/90.86% critical coverage, 34 frontend tests, zero runtime npm vulnerabilities, two non-root local images, and four healthy Compose services. It made no AWS change and did not run Terraform plan/apply, ECR/GitHub push, or RDS migration.

The monitoring input decision is complete: ignored `staging-prerequisites/terraform.tfvars` sets `info@nagi-neco.com` and a 100 GBP monthly Budget. CloudWatch ALB/ECS/worker/RDS alarms in main staging publish to the prerequisite `system-navigator-staging-alerts`; the email subscription remains `PendingConfirmation` until confirmed by a human. AWS Budgets sends actual 50/80/100% and forecasted 100% notices directly to the same address.
# 2026-08-03 quality-gate re-evaluation

Local clean Compose reconstruction, all three browser suites, accessibility, document/DB fault injection, worker competition, secret scanning, migration and OpenAPI checks pass. Staging is still **NOT_READY**: Ruff has 274 findings, important-service aggregate coverage is 85.72% against 90%, and the 50-user/60-second normal API p95 gate (500 ms) is not met. No staging action may begin until all are remediated and the deployment checklist receives its explicit approvals.

## 2026-08-06 resume gate result

The local implementation gate is **READY**: Backend 125 passed, overall 83.09% (minimum 80%), critical services 90.86% (minimum 90%), Frontend 34 passed above its 70% thresholds, migration `8d4f2a7c9b11` downgrade/upgrade/offline SQL/metadata checks passed, all four Compose services are healthy, and Chromium/Firefox/WebKit each passed 23 tests with axe critical/serious 0. Snapshot absence fails closed and billing/artifact/AI identities are idempotent.

This does not authorize staging. Git/image pinning, SQL/lock review, RDS snapshot, provider/security approvals, Terraform review, and named checklist approvers remain required before cloud action.
