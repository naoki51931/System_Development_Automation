# Production 100 RPM pre-apply safety

- Account/region/state: `557604519341` / `eu-west-2` / `cloud-a/prod/terraform.tfstate`
- Starting Git HEAD: `9a28fefd1820795afd1a38add64a66425daec7e2`
- Manual snapshot: `ai-platform-prod-pre-100rpm-downsize-20260812-010957`, available, 100%, encrypted, PostgreSQL 18.3, source `ai-platform-prod-postgres`.
- PITR: automated backup active, retention 14 days, restore window `2026-08-01T13:20:41.375Z` to `2026-08-12T01:02:29Z`. Instance Earliest was null but automated backup provides both bounds; Latest matched.
- RDS: available, `db.t4g.medium`, 50 GiB gp2, Multi-AZ, private/encrypted, deletion protection, backup 14 days. Planned class-only in-place change to `db.t4g.small`.
- Existing Production alarms/topics: 0/0. Proposed: isolated `ai-platform-prod-alerts`, 13 alarms, no subscription because recipient is unset.
- ECS rollback: active `ai-platform-prod:4`, 512 CPU/1024 MiB, image v4. Proposed low-traffic family is 256/512 with desired/min/max 1/1/2, CPU/memory targets 60/70, circuit breaker rollback, 100/200 deployment, 60-second grace.
- Maintenance: `apply_immediately=false` default; use `sat:02:43-sat:03:13`. Expect restart/failover/transient interruption. Roll back RDS to medium and ECS to revision 4 under separate reviewed plans.
- ALB and NAT remain active/available and have no plan action. Staging remains Idle and unchanged.
- Cost estimate: approximately USD 192/month before, USD 134 plus low alarm/Container Insights usage after, approximately USD 58/month saving. Combined with Staging: approximately USD 264–266/month.
- Apply: prohibited and not performed.

Gates: snapshot/PITR/performance/capacity/Multi-AZ/ALB/NAT/replace-zero/destroy-zero/rollback/maintenance/Staging/validate PASS. Notification is BLOCKED. Security is FAIL because pip-audit reports five findings in pip 25.0.1 in the Compose test image; Ruff and Bandit pass. Backend application tests pass 129, while eight infra file tests cannot run inside the allowlisted backend image and pass 22/22 on the host. Frontend 34 tests, build and OpenAPI check pass.

Final: `NOT_READY_FOR_PRODUCTION_100RPM_FINAL_APPLY_APPROVAL`.
