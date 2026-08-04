# SystemNavigator AI staging readiness

## Purpose and production differences

Staging validates deployment, identity, provider boundaries, migration, tenant isolation, observability, and rollback before production. It uses synthetic data only, separate accounts/resources/secrets, lower scaling, strict cost budgets, Cognito test users, Stripe test mode, and either SES Sandbox or Mailpit. Production customer data and production credentials are forbidden.

## Proposed services and approval points

A dedicated VPC/ALB/HTTPS service set would contain ECS backend/frontend/worker, ECR images pinned by digest, RDS PostgreSQL, a versioned S3 staging bucket, Cognito Test User Pool, Secrets Manager, CloudWatch logs/metrics/alarms, Route 53 staging DNS, Stripe Test Mode, and SES Sandbox. External AI stays Stub by default; any limited provider connection requires a separate data/security/cost approval. None of these resources are created in this phase.

Approval is required before: Terraform plan, any destroy/replacement, secret registration, RDS access/migration, ECR push, ECS deployment, DNS/HTTPS change, Cognito/Stripe/S3/SES connection, external AI enabling, or data reset. Set AWS Budgets alerts and service quotas before creation.

## Migration, seed and deploy order

1. Freeze a tested Git commit and immutable image digests.
2. Review offline migration SQL, locks and rollback classification; snapshot RDS.
3. Review a saved Terraform plan, with explicit destroy/replacement inventory.
4. Register staging-only Secrets Manager values and disable LocalAuth (`APP_ENV=staging`, `APP_LOCAL_AUTH_ENABLED=false`).
5. Push reviewed images, apply only the approved saved plan, and run one migration-only ECS task.
6. Run idempotent system/reference seed only; load synthetic test data separately.
7. deploy backend, worker, then frontend; verify ALB health, HTTPS, DNS and CloudWatch.
8. Execute tenant, billing-test, S3, document, email-sandbox, worker and alarm smoke tests.

S3 uses blocked public access, encryption, tenant-prefixed keys, CORS limited to the staging origin, lifecycle rules, and versioning. Stripe uses test keys/webhooks only. Cognito uses a separate pool and callback URLs. SES Sandbox restricts verified recipients; Mailpit remains the local alternative.

## Rollback

Application rollback selects the previous ECS task definitions and immutable image digests, then stops new workers if schema compatibility is uncertain. Prefer a forward fix for additive migrations. Downgrade is allowed only when offline SQL review proves it non-destructive and no newer data depends on it. Otherwise restore an RDS snapshot into a new instance and switch only after validation.

Preserve S3 versions and audit logs. Roll back Secrets Manager by version stage, restore Cognito configuration from reviewed export, disable Stripe webhooks before reverting consumers, stop workers before DB restoration, and switch DNS only after old-target health verification. Never erase audit evidence during reset or rollback.

## Final quality-gate recheck (2026-08-04)

The decision is **NOT_READY**. Ruff is clean, backend coverage is 81.43%, and list
API p95 passes. Critical-service coverage is 86.04% (required 90%), normal API p95
is 609 ms (required 500 ms), and npm audit is DNS-BLOCKED rather than PASS.

## Data, observability and cost

Use generated organizations/users/projects only, tagged with expiry. Reset by approved staging-specific procedure after exporting audit evidence. CloudWatch covers 5xx, latency, task restarts, worker lease age, retry/dead-letter count, RDS CPU/connections/storage and ALB health. Define monthly cost ceiling, daily anomaly alert, NAT/log retention limits and manual approval for scale increases.
# 2026-08-03 quality-gate re-evaluation

Local clean Compose reconstruction, all three browser suites, accessibility, document/DB fault injection, worker competition, secret scanning, migration and OpenAPI checks pass. Staging is still **NOT_READY**: Ruff has 274 findings, important-service aggregate coverage is 85.72% against 90%, and the 50-user/60-second normal API p95 gate (500 ms) is not met. No staging action may begin until all are remediated and the deployment checklist receives its explicit approvals.
