# Production 100 RPM capacity review

Collected 2026-08-11 in AWS account `557604519341`, `eu-west-2`. Production is VPC `10.20.0.0/16`, state `cloud-a/prod/terraform.tfstate`; Staging `10.30.0.0/16` was not planned or changed.

## Current inventory and traffic

Production ECS has one healthy Fargate service/task, task definition `ai-platform-prod:4`, 512 CPU/1024 MiB, desired/running 1, platform LATEST, rolling 100/200, grace 60 seconds, and no circuit breaker. There is no separate worker service. RDS is PostgreSQL 18.3, `db.t4g.medium`, 50 GiB gp2, Multi-AZ, private/encrypted, 14-day retention and deletion protection. ALB is internet-facing across two AZs; NAT is one gateway.

Over 14 days: 4,824 ALB requests, about 0.35 RPM average, 0.13 RPM median active 15-minute bucket, 19 RPM peak after 15-minute smoothing. The last-24-hour one-minute peak was 283 RPM. Target latency average was 2.24 ms; worst metric-window p95/p99 were 59.7/60.1 ms. Target 5xx was zero and ELB 5xx total was two.

ECS CPU average/max was 1.23/26.53%; memory 5.17/5.37%. RDS CPU average/max was 3.96/44.90%; minimum FreeableMemory 2.86 GiB; DatabaseConnections max 0; max read/write IOPS 12.2/57.7; max read/write latency 10/211 ms; minimum free storage 46.28 GiB. NAT traffic was only ~186 MiB in each observed direction, so fixed hours dominate.

## Isolated load test

No load reached Production. A local backend was constrained to 0.25 vCPU/512 MiB and used synthetic PostgreSQL data.

| Load | Effective | Requests/errors | p50/p95/p99 | Backend CPU average of allocation | Memory peak |
|---|---:|---:|---:|---:|---:|
| 100 RPM | 1.61 rps | 38 / 0 | 12/480/540 ms | 42% | 85.7 MiB |
| 300 RPM | 5.05 rps | 122 / 0 | 12/100/170 ms | 50% | 85.9 MiB |
| 600 RPM burst | 10.32 rps | 149 / 0 | 11/110/140 ms | 66–71% | 89.1 MiB |

At the repeated burst, local PostgreSQL CPU peaked at 7.08% with eight connections. Error rate was 0%. The one 540-ms p99 at 100 RPM was the one-time local user-list/login warm-up; list endpoint p95 stayed at or below 480 ms and all heavy/list targets remained below 1000 ms.

## Capacity choice

- Candidate A, 256 CPU/512 MiB: PASS and selected; smallest Fargate combination with memory at only ~17%.
- Candidate B, 256 CPU/1 GiB: unnecessary memory cost for measured ~89 MiB peak.
- Candidate C/current, 512 CPU/1 GiB: largest margin, but measured load does not justify double compute/memory.
- Desired/min 1 and max 2: lowest steady cost with target tracking CPU 60%, memory 70%, scale-out cooldown 60 seconds. One task reduces failure/deployment availability; max 2 and 100/200 rolling settings mitigate planned rollouts but not sudden single-task loss.
- Worker: absent today. Do not mix future AI/PDF/email/outbox backlog sizing with Web API evidence.
- RDS: `db.t4g.small`, Multi-AZ retained. `db.t4g.micro` is orderable but rejected due to 1-GiB memory, connection and burst-credit risk. Storage remains 50 GiB because RDS cannot shrink it in place.

## Cost alternatives

Cost Explorer is not resource-tag separable in this account, so figures use eu-west-2 usage-line monthly run rates and exclude unrelated EC2.

| Option | Approx/month | Saving | Margin/availability | Decision |
|---|---:|---:|---|---|
| Current | $192 | — | 512/1024, medium Multi-AZ | Baseline |
| A safe | $134 | $58 | 256/512 with max 2, small Multi-AZ | **Selected** |
| B cost | $109 | $83 | micro Multi-AZ; insufficient memory evidence | Reject |
| C future | TBD, potentially lower | larger | API Gateway/Lambda and NAT redesign | Separate phase |

Current estimated components: RDS ~$110, Fargate ~$19, ALB ~$18, NAT ~$34, public IPv4/control services ~$11. Safe profile halves RDS compute and steady Fargate, while leaving storage, ALB and NAT unchanged.

NAT removal is not in the plan. Compare NAT+S3 Gateway, selected Interface Endpoints, or reviewed public-task egress later. ALB removal/API Gateway is also a separate architecture project. Single-AZ is `SEPARATE_HIGH_RISK_APPROVAL_REQUIRED`.

## Testing and operational risk

Backend overall coverage is 82.89%; critical services 90.86%. Frontend 34 tests, OpenAPI drift check and production build pass. Ruff, Bandit, pinned project requirements pip-audit and tracked-file secret scan pass. Four Terraform roots validate.

RDS has 14-day retention and a latest restore time, but no Production manual snapshot was found and EarliestRestorableTime was null. No `ai-platform-prod*` CloudWatch alarms exist. Therefore an apply approval must require a new available manual snapshot, confirmed PITR window, maintenance/failover review, and a separate monitoring plan or explicit monitoring risk acceptance. This turn did not create either.

Rollback is the retained `ai-platform-prod:4` task definition for ECS and an in-place class change back to `db.t4g.medium` for RDS. RDS rollback may reboot/fail over; it is not data rollback.
