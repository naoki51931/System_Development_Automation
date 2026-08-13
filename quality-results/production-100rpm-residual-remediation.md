# Production 100 RPM residual remediation — 2026-08-12 UTC

The previous saved plan `production-100rpm-pitr-remediated-final.tfplan`, SHA-256 `6c4a977c54942c734526abc7f233124014a74eef861fc298f91f90b28b27efc3`, is **STALE / PARTIALLY_APPLIED / INVALID** and must never be reapplied. Its ECS, autoscaling, ALB/ECS alarms, SNS and Container Insights changes succeeded; AWS rejected the Multi-AZ RDS class change with `InsufficientDBInstanceCapacity` before the six RDS alarms were created.

Current AWS state is healthy: ECS `ai-platform-prod-low-traffic:1` is 256 CPU/512 MiB, desired/running 1/1, deployment COMPLETED, autoscaling 1–2, ALB target healthy, and all three GET smoke tests return 200. RDS is available on `db.t4g.medium`, with no pending modification, Multi-AZ in `eu-west-2a`/`eu-west-2b`, 50 GiB gp2, PostgreSQL 18.3, retention 14, deletion protection/encryption enabled and public access disabled.

## Capacity classification

RDS `OrderableDBInstanceOptions` confirms `db.t4g.small` with PostgreSQL 18.3 is Multi-AZ capable and orderable with gp2 in `eu-west-2a`, `eu-west-2b`, and `eu-west-2c`. This API proves configuration support, not instantaneous inventory. Combined with the prior explicit `InsufficientDBInstanceCapacity` response, the classification is **CLASS_SUPPORTED_CAPACITY_TEMPORARILY_UNAVAILABLE**.

`db.t3.small` is also orderable for the same engine/version, Multi-AZ, gp2 and all three AZs. It is an alternative requiring separate cost/architecture review and human approval; this remediation retains `db.t4g.small` as the first retry candidate. Recommendation: **RETRY_SAME_CLASS_RECOMMENDED**, with the acknowledged risk that maintenance scheduling can encounter the same transient capacity shortage. No retry or apply occurred in this turn.

PITR Gate remains PASS with only `PITR_API_FIELD_WARNING` for the null DB-instance field. The pre-change manual snapshot remains available, 100% and encrypted. Production currently has seven alarms (ALB 4, ECS 3, all OK) and no RDS alarms. SNS `ai-platform-prod-alerts` exists; the `info@nagi-neco.com` email subscription remains PendingConfirmation. Staging remains `STAGING_IDLE_MODE_CONVERGED` with RDS, ALB, Interface Endpoints and runtime ECS all zero.

## Cost separation

The reviewed baseline was approximately $192/month: RDS $110, Fargate $19, ALB $18, NAT $34 and other/control services $11. Halving steady Fargate plus the seven alarms and variable Container Insights gives a current partial-state estimate of approximately **$183–184/month**, or approximately $8–9/month already realized. The fully monitored target remains approximately **$135–136/month**. Completing the RDS change and six alarms therefore represents approximately **$48/month remaining saving**. These are configuration-derived estimates; Cost Explorer has reporting lag and is not resource-tag separable here.
