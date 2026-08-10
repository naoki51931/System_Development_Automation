# Staging deployment checklist

## Before apply

- [x] Read-only discovery confirmed account `557604519341`, region `eu-west-2`, state backend/KMS, production inventory, and staging name non-collision
- [ ] Create/approve staging ECR repositories and publish reviewed backend/worker/frontend image digest; `57109fa` is currently absent
- [ ] Approve the two-repository design (`staging-app`, `staging-frontend`) and prerequisites state; do not use routine `-target`
- [ ] Review one prerequisites plan containing only ECR, staging deploy IAM, SNS subscription, and Budget; custom-domain ACM/DNS remains disabled
- [ ] Copy approved prerequisite ECR URLs/role/SNS outputs into ignored main staging inputs; never add a reverse state dependency
- [ ] Require ECR scan critical/high = 0 and copy registry digests—not local image IDs—into ignored tfvars
- [ ] Create/approve staging-only GitHub role restricted to the repository `staging` environment
- [ ] Configure GitHub Environment branch protection for `agent/final-quality-gate` or approved `main`
- [x] Alert target is `info@nagi-neco.com`; Budget is 150 USD; values remain in ignored tfvars
- [ ] Approve no-NAT endpoints or explicitly approve EIP quota/cost for a NAT alternative
- [x] Approve Budget amount/currency: 150 USD (AWS rejected the former 100 GBP setting; this account accepts USD only)
- [ ] After an approved apply, manually confirm the SNS email subscription; expect `PendingConfirmation` before confirmation
- [x] Exclude SES inbound, MX changes, receiving S3/Inbox API, and `nagi-neco.com` DNS/mail changes
- [ ] Confirm production key remains `cloud-a/prod/terraform.tfstate` and staging key is `system-navigator/staging/terraform.tfstate`
- [ ] Replace every `REPLACE_*` value outside Git; confirm staging S3/RDS names differ from production
- [ ] Select dedicated VPC (recommended) or review existing VPC/subnet/SG blast radius
- [ ] Pin Git commit and image digests; all quality gates pass
- [ ] Review offline migration SQL, lock duration and forward-fix/downgrade decision
- [ ] Review saved Terraform plan and every destroy/replacement target
- [ ] Take and verify RDS snapshot; define restore target
- [ ] Register staging-only Secrets Manager values
- [ ] Disable LocalAuth and local Mock providers where staging integration is approved
- [ ] Confirm Cognito Test Pool and callbacks; Stripe Test Mode only
- [ ] Review S3 CORS/public-block/versioning and SES Sandbox recipients
- [ ] Configure CloudWatch alarms, log retention, budget and anomaly notifications
- [ ] Record approvals for AWS, RDS, provider connection, plan and migration
- [x] Confirm `true-camera-test.com` is not used and custom domain/ACM/Route53/HTTPS are disabled pending a new-domain approval
- [ ] Restrict temporary ALB HTTP checks to non-production, non-customer, mock-only, non-sensitive use
- [ ] Confirm mock-provider banner/indicators are visible while mocks remain enabled

## During apply

- [ ] Phase 1: apply only a reviewed bootstrap plan with `enable_runtime_services=false`; create infrastructure and task definitions but no runtime ECS services
- [ ] Phase 2: under separate human approval, populate the application DB Secret outside Terraform; never manage its value in state
- [ ] Confirm RDS readiness plus backup/PITR before migration
- [x] Remove the non-persistent empty Cloud Map custom-health block; reconcile plan confirms backend and worker discovery are no-op
- [ ] Require concrete RDS earliest and latest restorable timestamps (latest exists; earliest remains null as of 2026-08-10)
- [ ] Phase 3: run the separately approved migration-only task; capture output and schema revision
- [ ] Stop deployment if migration exits non-zero or Alembic head is not confirmed
- [ ] Phase 4: review a new `enable_runtime_services=true` plan with backend/worker/frontend desired count 1
- [ ] Phase 5: apply only that reviewed runtime-service plan and verify backend `/health`, frontend `/login`, and worker health
- [ ] Run idempotent reference seed and separate synthetic test-data seed
- [ ] Verify temporary ALB HTTP smoke endpoints; verify HTTPS/DNS only after a new domain is approved
- [ ] Stop immediately on unexpected replacement, secret exposure or tenant failure

## After apply

- [ ] Cognito login/logout and tenant boundary
- [ ] Estimate, contract and Stripe Test payment
- [ ] Tenant-safe S3 upload/download and PDF generation
- [ ] SES Sandbox test email to approved recipient
- [ ] External AI remains Stub unless separately approved
- [ ] Worker claim, lease expiry, retry and dead letter
- [ ] CloudWatch logs/metrics/alarms and budget notification
- [ ] Validate old ECS task rollback and DB restore runbook
- [ ] Preserve audit logs and record evidence/approvers
# Current blocking gate

- [x] `quality-results/quality-gate-summary.md` is READY_FOR_PRE_PLAN_RESOURCE_APPROVAL.
- [x] Ruff lint is clean (0 findings).
- [x] Backend overall coverage is at least 80% (currently 83.09%).
- [x] Important-service aggregate coverage is at least 90% (currently 90.86%).
- [x] Normal project-detail p95 is at most 500 ms at 50 users for 60 seconds (currently 490 ms).
- [x] Worker health and explicit dispatch are active; all four Compose services are healthy.
- [x] Document/AI workflow snapshot-based resume is automatic; legacy rows without snapshots fail closed by design.
- [x] Dependency security audit completes without unresolved findings (npm audit: 0).

Do not proceed to AWS/Terraform/Cognito/Stripe/S3/SES steps while any item above is unchecked.

`terraform plan` itself requires named human approval. An approved plan must show no production address, state migration, `moved`/import block, or replacement of the running production ALB/ECS/RDS/S3/VPC. Apply requires a second approval of the saved plan. Rollback must identify the prior immutable task revisions, schema compatibility decision, worker stop point, and snapshot restore-to-new-instance path.

## 2026-08-05 recheck

- [x] Ruff and undefined symbols: 0.
- [ ] Backend coverage: 79.86% (required 80%).
- [ ] Critical-service coverage: 86.02% (required 90%).
- [x] Normal project-detail p95: 490 ms (required at most 500 ms).
- [x] List API worst p95: 540 ms (required at most 1 second).
- [x] Compose worker health and explicit dispatch: PASS.
- [ ] Safe partial document/AI workflow resume: FAIL.
- [x] npm audit: PASS; PostCSS 8.5.23, zero vulnerabilities.

The authoritative result is **NOT_READY**.

## 2026-08-06 resume completion recheck

- [x] Backend 140 passed; overall 83.09% and critical services 90.86% (1560/1717).
- [x] Immutable snapshot/step triggers, schema version `1`, deterministic version/run/review/cost identities, hash validation, and missing-snapshot fail-closed tests pass.
- [x] Migration `8d4f2a7c9b11`: downgrade, upgrade, offline SQL, and metadata drift checks pass.
- [x] Compose services healthy; reference seed succeeds twice.
- [x] Chromium/Firefox/WebKit 23/23 each; axe critical/serious 0.
- [x] Ruff, Security, Secret Scan, OpenAPI, and npm audit pass.
- [ ] Pin Git commit/image digests and obtain every AWS/RDS/provider/Terraform approval above.

Local software quality is **READY**. Staging migration remains prohibited until the remaining approval/deployment prerequisites are checked.
