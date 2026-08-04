# Staging deployment checklist

## Before apply

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

## During apply

- [ ] Apply only the reviewed saved plan
- [ ] Run migration-only task; capture output and schema revision
- [ ] Run idempotent reference seed and separate synthetic test-data seed
- [ ] Deploy backend, worker and frontend pinned task definitions
- [ ] Verify ALB health, HTTPS certificate, DNS and smoke endpoints
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

- [ ] `quality-results/quality-gate-summary.md` is READY (currently NOT_READY).
- [ ] Ruff lint is clean (currently 274 findings).
- [ ] Important-service aggregate coverage is at least 90% (currently 85.72%).
- [ ] Normal API p95 is at most 500 ms at 50 users for 60 seconds (currently cold aggregate 600 ms; warm 890 ms).

Do not proceed to AWS/Terraform/Cognito/Stripe/S3/SES steps while any item above is unchecked.

## 2026-08-04 recheck

- [x] Ruff and undefined symbols: 0.
- [ ] Critical-service coverage: 86.04% (required 90%).
- [ ] Normal API p95: 609 ms (required 500 ms).
- [x] List API worst p95: 684 ms (required at most 1 second).
- [ ] npm audit: DNS-BLOCKED; not PASS.

The authoritative result is **NOT_READY**.
