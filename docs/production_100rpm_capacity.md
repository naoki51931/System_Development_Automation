# Production 100 RPM capacity profile

The reviewed `low-traffic` profile targets 100 requests/minute continuously, 300 RPM safety load, and a short 600 RPM burst. It uses one 0.25-vCPU/512-MiB backend task with autoscaling min 1/max 2, CPU target 60%, memory target 70%, and a 60-second scale-out cooldown. A single task is lowest cost but has reduced fault/deployment redundancy; rolling deployment temporarily permits two tasks and the circuit breaker rolls back failed health.

The current 0.5-vCPU/1-GiB task definition remains registered. Low traffic uses a separate family so rollback is an ECS service update to the known-good revision, not a rebuild. There is no separate Production worker service today; introducing AI/PDF/email/outbox workers requires independent queue/backlog sizing.

RDS changes only from `db.t4g.medium` to `db.t4g.small`. Multi-AZ, 50 GiB gp2, backups, encryption, private networking and deletion protection remain. `db.t4g.micro` is orderable but rejected because its 1-GiB memory/connection/burst-credit margin is not sufficient evidence for Production. Storage cannot be reduced in place. Single-AZ is `SEPARATE_HIGH_RISK_APPROVAL_REQUIRED`.

ALB and the single NAT Gateway remain unchanged. NAT carried only about 0.36 GiB over the observed 14 days, so fixed gateway hours dominate. A future phase can compare selected endpoints/public tasks, and a larger redesign can compare API Gateway/Lambda, but neither belongs in this capacity plan.

Before any apply: capture a Production manual snapshot, require available status, verify automated backup/PITR including a non-null earliest restore point, review maintenance/failover impact, and confirm the saved plan checksum. After apply, watch ALB 5xx/latency, ECS CPU/memory, RDS CPU/connections/free memory/read-write latency and scaling events. The account currently has no `ai-platform-prod*` alarms, so alarm creation is a separate required monitoring change.

Rollback:

1. ECS: update the service to `ai-platform-prod:4`, wait for healthy target/rollout completion, and keep desired count at least one.
2. RDS: modify class back to `db.t4g.medium`; expect a Multi-AZ failover/restart window. This is capacity rollback, not data rollback.
3. Stop if RDS CPU is sustained above 70%, ECS CPU/memory above 80%, error rate reaches 1%, normal p95 exceeds 500 ms, list p95 exceeds 1000 ms, or DB connection/free-memory margin deteriorates.
