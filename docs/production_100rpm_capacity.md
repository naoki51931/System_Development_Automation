# Production 100 RPM capacity profile

The reviewed `low-traffic` profile targets 100 requests/minute continuously, 300 RPM safety load, and a short 600 RPM burst. It uses one 0.25-vCPU/512-MiB backend task with autoscaling min 1/max 2, CPU target 60%, memory target 70%, and a 60-second scale-out cooldown. A single task is lowest cost but has reduced fault/deployment redundancy; rolling deployment temporarily permits two tasks and the circuit breaker rolls back failed health.

The current 0.5-vCPU/1-GiB task definition remains registered. Low traffic uses a separate family so rollback is an ECS service update to the known-good revision, not a rebuild. There is no separate Production worker service today; introducing AI/PDF/email/outbox workers requires independent queue/backlog sizing.

RDS changes only from `db.t4g.medium` to `db.t4g.small`. Multi-AZ, 50 GiB gp2, backups, encryption, private networking and deletion protection remain. `db.t4g.micro` is orderable but rejected because its 1-GiB memory/connection/burst-credit margin is not sufficient evidence for Production. Storage cannot be reduced in place. Single-AZ is `SEPARATE_HIGH_RISK_APPROVAL_REQUIRED`.

ALB and the single NAT Gateway remain unchanged. NAT carried only about 0.36 GiB over the observed 14 days, so fixed gateway hours dominate. A future phase can compare selected endpoints/public tasks, and a larger redesign can compare API Gateway/Lambda, but neither belongs in this capacity plan.

Before any apply: capture a Production manual snapshot, require available status, verify automated backup/PITR including a non-null earliest restore point, review maintenance/failover impact, and confirm the saved plan checksum. After apply, watch ALB 5xx/latency, ECS CPU/memory, RDS CPU/connections/free memory/read-write latency and scaling events. The account currently has no `ai-platform-prod*` alarms, so alarm creation is a separate required monitoring change.

The safety design adds a dedicated `ai-platform-prod-alerts` SNS topic and 13 alarms: ALB target/ELB 5xx, unhealthy hosts and p95 response time; ECS CPU, memory and running task count; RDS CPU, connections, free memory/storage and read/write latency. The thresholds are based on the observed low utilization and the reviewed SLO: p95 500 ms, any unhealthy host, ELB 5xx >=1/5 min, target 5xx >=5/5 min, ECS CPU/memory 80%, RDS CPU 70%, connections 80, free memory 512 MiB, free storage 5 GiB, and read/write latency 50 ms sustained for ten minutes. The approved Production recipient is `info@nagi-neco.com`; Terraform disables automatic confirmation, so a human must confirm the AWS email subscription after apply. Staging may use the same recipient but remains isolated on `system-navigator-staging-alerts`; topics and alarms are never shared.

The reviewed remediated plan is `production-100rpm-remediated-final.tfplan`, SHA-256 `d6f094ded385f70628f9e0840e86c051fc2308d78a6afc313d5aafe32e8a5df0`, with 19 add / 3 change / 0 replace / 0 destroy. It is review-only until separately approved. The prior `production-100rpm-final.tfplan` is stale/invalid.

The RDS class update uses the provider default `apply_immediately=false`, so it waits for the existing `sat:02:43-sat:03:13` maintenance window. Expect a restart or Multi-AZ failover and transient connection interruption. Roll back by a separately reviewed class update to `db.t4g.medium`; data recovery uses PITR or the retained pre-change snapshot only if required. ECS retains `ai-platform-prod:4` (512/1024) as the known-good rollback revision, enables circuit-breaker rollback, keeps 100/200 deployment percentages and a 60-second health grace period. CPU/memory target tracking is sufficient at 100 RPM; request-count scaling would add noise and complexity at the observed ~0.35 RPM average and is not proposed.

Rollback:

1. ECS: update the service to `ai-platform-prod:4`, wait for healthy target/rollout completion, and keep desired count at least one.
2. RDS: modify class back to `db.t4g.medium`; expect a Multi-AZ failover/restart window. This is capacity rollback, not data rollback.
3. Stop if RDS CPU is sustained above 70%, ECS CPU/memory above 80%, error rate reaches 1%, normal p95 exceeds 500 ms, list p95 exceeds 1000 ms, or DB connection/free-memory margin deteriorates.
