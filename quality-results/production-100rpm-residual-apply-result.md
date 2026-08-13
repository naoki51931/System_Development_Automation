# Production RDS small residual apply result — 2026-08-12 UTC

## Authorization and apply

- Git HEAD at start: `db4f40623946b8507aaf72203997a17f8ea50670`; worktree clean.
- AWS account `557604519341`, region `eu-west-2`, role `instanceRoleTerraform`.
- State key: `cloud-a/prod/terraform.tfstate`.
- Applied exactly once: `environment/production-100rpm-residual.tfplan`.
- SHA-256: `992ec5ffb8ec5da4383b29c23e908689db7f4339bb4eccc71f18f0dc3bbc5578`; exact match.
- Terraform result: **6 added / 1 changed / 0 destroyed**; no capacity error and no retry.

All preflight gates passed: ECS was healthy on `ai-platform-prod-low-traffic:1` at 256 CPU/512 MiB with desired/running 1/1 and autoscaling 1–2; GET `/`, `/health`, and `/docs` returned 200; PITR passed; the manual snapshot was available/100%/encrypted; and PostgreSQL 18.3 `db.t4g.small` remained Multi-AZ/gp2 orderable in eu-west-2a/b/c. The plan contained only the in-place RDS class update and six RDS alarms.

## Post-apply state

RDS modification scheduling succeeded. Because `apply_immediately=false`, the DB remains `db.t4g.medium` and `PendingModifiedValues.DBInstanceClass` is `db.t4g.small`. Classification: **RDS_DOWNSIZING_PENDING_MAINTENANCE**. The maintenance window remains `sat:02:43-sat:03:13` UTC. Multi-AZ true, 50 GiB gp2, PostgreSQL 18.3, retention 14, deletion protection/encryption true, and public access false are preserved.

PITR post-check is PASS with only `PITR_API_FIELD_WARNING` for the null DB-instance field. The named manual snapshot remains available, 100% and encrypted.

All 13 Production alarms exist: ALB 4, ECS 3 and RDS 6. Eight are OK and five newly created RDS alarms are initially INSUFFICIENT_DATA; no alarm is ALARM. The RDS FreeableMemory alarm already reached OK. Initial INSUFFICIENT_DATA is expected while CloudWatch evaluates new metrics.

SNS `ai-platform-prod-alerts` is preserved. The email endpoint is `info@nagi-neco.com` and remains PendingConfirmation; automatic confirmation was not attempted.

ECS remains `ai-platform-prod-low-traffic:1`, 256 CPU/512 MiB, desired/running 1/1, deployment COMPLETED and target healthy. All three GET smoke tests remain 200 with `/health` returning `{"status":"ok"}`. ALB is active and NAT is available. Staging remains `STAGING_IDLE_MODE_CONVERGED`: RDS, ALB, Interface Endpoints and runtime ECS are all zero.

The read-only post-apply Terraform plan returned detailed exit code 2 with **0 add / 1 change / 0 destroy**. The sole apparent change is the same medium-to-small class transition while AWS holds it in pending maintenance. Classification: **POST_APPLY_PLAN_PENDING_RDS_MAINTENANCE**. No additional apply was performed.

## Cost and decision

The current configuration remains approximately $183–184/month until the maintenance change completes. The final target is approximately $135–136/month, with approximately $48/month remaining from the pending RDS change, $56–57/month total Production saving, and $262–265/month combined with Staging.

Decision:

- **PRODUCTION_100RPM_DOWNSIZING_APPLIED**
- **RDS_DOWNSIZING_PENDING_MAINTENANCE**
- **MANUAL_SNS_CONFIRMATION_REQUIRED**

Human actions: confirm the SNS email subscription, then after the maintenance window verify RDS is `db.t4g.small`, safety/PITR remain intact, alarms settle without ALARM, and a fresh read-only Terraform plan is no-op.
