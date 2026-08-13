# AWS cost optimization read-only investigation — 2026-08-10

## Executive conclusion

Collected at `2026-08-10T14:56:15Z` for account `557604519341`, role `instanceRoleTerraform`, region `eu-west-2`. Only AWS CLI `get`, `list`, and `describe` operations and Cost Explorer reads were used. No AWS resource, Secret value, database, Terraform, or GitHub mutation was performed.

August 1–10 Cost Explorer data is estimated and subject to billing delay. The observed unblended total is **$80.07**, including **Tax $7.28**. Staging was created around 13:48–13:52 UTC today, after most currently visible billing data, so its new fixed cost is mostly absent from the $80.07.

The new staging design has a serious fixed-cost issue: seven Interface VPC Endpoints, each in two AZs, represent 14 endpoint-AZ-hours. At the eu-west-2 rate inferred for this configuration (`$0.0125/endpoint-AZ-hour`), this is about **$0.175/hour, $4.20/day, or $127.75 per 730-hour month**, before data processing. This one line can consume about 85% of the $150 staging budget.

### Required priority statement

**削減優先順位 1位:** Staging Interface VPC Endpoints (7 endpoints × 2 AZ) — estimated **$127.75/month**. Delete through reviewed Terraform when staging is unused; S3 Gateway Endpoint itself is free.

**削減優先順位 2位:** `system-navigator-staging-db` — estimated **about $54.9/month** while available. Stop for short idle windows; for sustained near-zero staging, retain a final snapshot and recreate through Terraform (destructive workflow requiring separate approval).

**削減優先順位 3位:** `system-navigator-staging-alb` plus its two public IPv4 addresses — estimated **about $26.62/month**. Delete through reviewed Terraform when staging runtime is disabled.

**今日止めても安全なもの:** From an infrastructure dependency perspective, the staging ECS runtime is already zero. A short-term stop candidate is the staging RDS **only after confirming no migration/task is running and recovery timing is acceptable**. The work EC2 `i-0add395a2d89805b5` is also a stop candidate when this investigation/session is finished. No stop was executed. Interface endpoints and ALB cannot be “stopped”; they require deletion and later recreation.

**今は止めない方がいいもの:** Production RDS, production ECS task/service, production ALB, production NAT Gateway and its EIP, production Secret, production artifact/state storage, and the currently used work EC2 until work is complete. Do not remove staging RDS before a recovery artifact and Terraform/state procedure are reviewed.

## Cost Explorer reconciliation

| Service | Aug 1–10 observed | Environment attribution | Usage Type / Operation |
|---|---:|---|---|
| Amazon RDS | $33.5285 | Production $33.5285; Staging $0 visible; Shared/Unknown $0 | Multi-AZ `db.t4g.medium` $29.8233 / 205.6781 h; Multi-AZ gp2 $3.6946 / 13.8897 GB-mo; brief single-AZ instance/storage $0.0105; transfer $0 |
| EC2 - Other | $11.9532 | Production NAT $10.4680; Shared/Unknown EBS $1.4695; transfer $0.0158; Staging $0 visible | NAT hours $10.4000 / 208 h; NAT bytes $0.0680 / 1.359 GB; gp3 $1.4695 / 15.835 GB-mo; regional/public transfer about $0.0158 |
| EC2 Compute | $10.3178 | Shared/Unknown EC2; not Production/Staging VPC | t3.small $5.1592 / 218.612 h; t3.medium $4.8941 / 103.688 h; historical t3.large $0.2645 / 2.802 h; transfer about $0.00001 |
| Amazon ECS | $5.8626 | Production $5.8626; Staging $0 | Fargate vCPU $4.8034 / 103.166 vCPU-h; memory $1.0544 / 206.332 GB-h; regional transfer $0.0048 |
| Elastic Load Balancing | $5.4777 | Production $5.4777; Staging $0 visible | ALB hours $5.4772 / 207 h; LCU $0.0005; transfer negligible |
| Amazon VPC | $4.7413 | Mostly Production/Shared public IPv4; Staging not yet visible | in-use EIP $4.2013 / 840.264 h; instance public IPv4 $0.5394 / 107.881 h; idle $0.0006 |
| Tax | $7.2800 | Account-level, not safely attributable to resources | Tax |
| Route 53 | $0.5020 | Shared/Unknown | hosted zone about $0.50 plus queries |
| KMS | $0.2769 | Shared/Production | key and requests; detailed total is small |
| Secrets Manager | $0.1114 | Production to date; new staging secrets not yet visible | secret-month prorating and requests |
| ECR | $0.0234 | Production dominant; Staging images only since Aug 9 | 1.385 GB current compressed image total; storage billed by GB-month |
| S3 | $0.0007 | Shared/Production | storage/requests negligible; state bucket measured 842,291 bytes |
| CloudWatch | $0.0000 | Production/Shared | 0.0062 GB ingestion and negligible storage, within free tier/current zero charge |
| Other zero/negligible | ~$0.0000 | Shared/Unknown | ACM $0, Glue $0, SNS $0, DynamoDB $0.000007 |

The displayed RDS $33.53 is therefore **effectively 100% production** for the visible interval. Staging RDS was created at `2026-08-10T13:52:00Z`; billing delay means its initial hours are not yet in Cost Explorer. Resource-level Cost Explorer data is not enabled for this payer account, so exact resource-ID billing was unavailable without changing account settings.

## Current inventory and monthly run rate

Monthly estimates use 730 hours and current on-demand configuration. They exclude tax and are directional; actual August cost depends on creation/deletion time and data volume.

| Resource | Env | Current visible cost | Estimated monthly | Saving if stopped/deleted | Production impact | Recovery | Terraform impact | Stop/deletion risk |
|---|---|---:|---:|---:|---|---|---|---|
| 7 staging Interface Endpoints in 2 AZs | Staging | $0 visible (created today) | **$127.75 + data** | ~$127.75 | None if production routes do not use staging VPC | Terraform recreate; tasks lose private AWS API access until restored | Managed by staging state; manual deletion causes drift, so use reviewed Terraform change | High functional impact to private ECS/migration; no stop API |
| `system-navigator-staging-db` db.t4g.small Single-AZ, 20 GB gp3 | Staging | $0 visible | **~$54.9** (~$52.6 compute + ~$2.3 storage) | stop: ~$52.6 while stopped, storage remains; snapshot/delete: nearly full amount | None | Start stopped DB (AWS auto-starts after 7 days), or recreate/restore snapshot | Stop causes state/runtime drift; deletion/recreate must be designed in Terraform and protect data | Medium/high; DB availability and possible data loss if deletion workflow is wrong |
| `system-navigator-staging-alb` | Staging | $0 visible | **$19.32 ALB + $7.30 IPv4 = $26.62** plus LCU | ~$26.62 | None | Terraform recreate, DNS name may change | Managed by staging state; deletion outside Terraform causes drift | Medium; staging ingress unavailable; no stop API |
| `ai-platform-prod-postgres` db.t4g.medium Multi-AZ, 50 GB gp2 | Production | **$33.5285** | **~$117.7** | up to compute portion while stopped, but not recommended | Critical production outage | Start DB; deletion requires snapshot restore | Production root/state; deletion/reconfiguration is high-risk | Critical |
| `ai-platform-prod` NAT Gateway | Production | **$10.4680** | **~$36.50 + data** | ~$36.50 | Critical for current private-task internet egress/image/runtime patterns | Terraform recreate and route restoration | Production state; route/NAT architecture change required | High |
| Production ALB | Production | **$5.4777** | **~$26.62 including 2 IPv4** | ~$26.62 | Critical public outage | Terraform recreate; DNS name may change | Production state | Critical |
| Production Fargate task (0.5 vCPU, 1 GB) | Production | **$5.8626** | **~$20.72** | ~$20.72 | Critical application outage | Set service desired count back through approved deployment | Production state/service desired count | Critical |
| `i-0add395a2d89805b5` t3.medium work EC2 | Shared/Unknown (work) | **~$4.8941 inferred** | **$34.46 compute + $2.78 EBS + up to $3.65 IPv4** | stop saves ~$38.11 compute/IP; EBS remains ~$2.78 | None known | Start instance; ephemeral public IP changes | Not found in product Terraform inventory | Medium; ends this workspace/session and any local processes |
| `i-0b08ca7468f7d5e1e` t3.small `nagineco homepage` | Shared/Unknown | **$5.1592 inferred** | **$17.24 compute + $1.86 EBS + $3.65 EIP** | stop saves compute; EIP can continue charging | No production platform impact, but homepage outage | Start instance; retain/reassociate EIP | Outside identified Terraform roots | High business impact if homepage is public |
| historical t3.large | Unknown | **$0.2645** | $0 current | $0 | Unknown | Not currently present | Unknown | Attribution unavailable; likely terminated/resized historical usage |
| stopped `i-05cb209b355a1c864` t3.micro | Shared/Unknown | $0 compute | **$0 compute + $0.74 EBS** | volume deletion saves ~$0.74 | None known | Snapshot/AMI or recreate | Outside identified Terraform roots | Data loss risk if volume deleted |
| All EC2 gp3 volumes: 30+20+8 GB | Shared/Unknown | **$1.4695** | **~$5.38** | only deletion saves; stopping does not | None to production platform | Restore snapshot/recreate; no snapshots currently exist | Outside identified Terraform roots | High data-loss risk; all are unencrypted and attached |
| EBS snapshots | Shared/Unknown | $0 | $0 | $0 | None | N/A | N/A | There are no account-owned snapshots in eu-west-2 |
| Public IPv4/EIP, current 6 addresses | Mixed | **$4.7413** | **~$21.90** at six continuously allocated/in-use IPs | $3.65/IP-month removed | Depends on owner | Reallocate/reassociate; address may change | ALB/NAT addresses follow resource lifecycle; other EIP/instance is external | Connectivity/DNS risk |
| ECR images (1.385 GB compressed) | Mixed | **$0.0234** | **~$0.14** | negligible | Removing active digest breaks deployment/rollback | Re-push exact digest if retained locally | Repositories Terraform-managed; lifecycle policy preferable | Supply-chain/rollback risk |
| Secrets Manager, 3 secrets | Mixed | **$0.1114** | **up to ~$1.20** plus calls | small | Production secret is critical; staging secrets needed for DB/runtime | Recreate metadata and securely repopulate value | Terraform owns containers, not values | High; value recovery may be impossible |
| CloudWatch logs/alarms | Mixed | $0 | near $0 at current volume | negligible | Loss of observability | Recreate config; logs cannot be recovered if deleted | Staging/prod managed separately | Monitoring/audit loss |
| S3 buckets | Mixed | $0.0007 | near $0 at current volume | negligible | State/artifact loss can be catastrophic | Version recovery/backup only | Terraform state bucket is foundational | Critical despite tiny cost |

Public IP ownership now is: Production NAT 1, Production ALB 2, Staging ALB 2, homepage EIP 1, and work-instance ephemeral public IP 1 would appear to total 7 logical addresses; however the live ENI inventory returned six public IPs because the homepage address is one of the five allocated EIPs and the current interface list contains Production ALB (2), Staging ALB (1 observed ENI at collection time), NAT (1), homepage (1), and work EC2 (1). ALB address count can change with node scaling. Use the billed public-IP hours, not a static count, for invoice reconciliation.

## Answers to the requested questions

1. **Biggest saving:** staging Interface Endpoints, ~$127.75/month.
2. **Second:** staging RDS, ~$54.9/month available run rate.
3. **Third:** staging ALB plus its public IPv4, ~$26.62/month.
4. **RDS $33.53 split:** Production $33.5285; Staging $0 yet visible; Shared/Unknown $0. Staging begins accruing today and is delayed.
5. **EC2 - Other $11.95:** NAT $10.4680, EBS gp3 $1.4695, and network transfer ~$0.0158.
6. **EC2 Compute $10.32:** t3.small/homepage ~$5.1592; t3.medium/work EC2 ~$4.8941; historical t3.large $0.2645; transfer ~$0.00001. Exact resource ID is inferred because CE resource-level data is disabled.
7. **ECS $5.86:** Production Fargate only: 0.5 vCPU/1 GB task, vCPU $4.8034, memory $1.0544, transfer $0.0048. Staging services/tasks are zero.
8. **VPC Endpoint impact:** ~$127.75/month for seven Interface Endpoints across two AZs; S3 Gateway Endpoint $0/hour; data processing extra.
9. **ALB impact:** each idle ALB ~$19.32/month plus ~$7.30/month for two public IPv4 addresses, about $26.62 before LCU/data. Production currently billed $5.4777; staging starts today.
10. **Public IPv4/EIP:** $4.7413 observed; rate is $0.005/IP-hour, or $3.65 per continuously held IP-month. Six public IPs were on live ENIs at collection time (~$21.90/month), subject to ALB node count.
11. **EBS:** $1.4695 observed for gp3; 58 GB current volumes imply ~$5.38/month. No owned EBS snapshots and no snapshot charge were found. RDS storage is reported under RDS, not EBS.
12. **Keep on unused staging days:** Terraform remote state, staging ECR active digests, minimal S3 configuration/data, IAM/task definitions, VPC/subnets/security groups/route tables (no direct hourly charge), S3 Gateway Endpoint (no hourly charge), Budget, and only recovery-critical secrets/snapshots.
13. **Stop/delete candidates on unused days:** stop staging RDS for <=7-day idle windows; delete/recreate Interface Endpoints and ALB for longer idle periods; ECS is already zero. For near-zero long-term staging, snapshot then remove RDS only under an approved data-recovery/Terraform workflow.
14. **Reduction while maintaining production:** staging fixed estate about **$210/month** (endpoints $127.75 + RDS ~$54.9 + ALB/IPv4 ~$26.62 + secrets/ECR minor). Including stopping the work EC2 when unused adds about **$38/month** compute/IP savings while its EBS remains, for **roughly $248/month** potential. This excludes tax effects.
15. **Minimum staging maintenance:** keeping only metadata/state, ECR images, S3, VPC primitives, S3 Gateway Endpoint, necessary secrets and a 20-GB RDS snapshot is approximately **$2–4/month**. Keeping the live stopped RDS adds storage (~$2.3/month) and it auto-starts after seven days; keeping it continuously available makes the floor about **$55–57/month** even after endpoints/ALB are removed.
16. **Three scenarios:** see below.

## Scenarios

| Scenario | Staging configuration | Estimated staging monthly | Savings vs current staging run rate (~$210) | Risk/recovery |
|---|---|---:|---:|---|
| Safety first | Keep endpoints, ALB, and RDS; ECS remains 0 | ~$210 | ~$0 | Fastest activation; budget likely exceeded by fixed costs alone |
| Cost focused | Remove Interface Endpoints and ALB; stop RDS during short idle periods; keep VPC/state/images/secrets | ~$3–6 while RDS is stopped, but AWS auto-starts after 7 days | up to ~$204 for genuinely idle periods | Recreate endpoints/ALB through Terraform; restart DB; staging unavailable while off |
| Minimum maintenance | Retain state/config/ECR/S3 and a verified DB snapshot; remove live RDS, ALB and Interface Endpoints | ~$2–4 | ~$206–208 | Slowest recovery; requires snapshot restore, Terraform recreation, DNS/health validation; highest operational/data risk |

For frequent on/off usage, seven two-AZ endpoints are economically unfavorable. A reviewed architecture comparison should consider NAT, endpoint consolidation/removal, or public-IP/egress patterns, but security and image/Secrets/Logs access requirements must be modeled before any change.

## Limitations and confidence

- Cost Explorer results are estimated and delayed; same-day staging cost is not yet reliable.
- Resource-level Cost Explorer returned `AccessDeniedException` because resource granularity is an opt-in feature. Enabling it would be an account setting change and was not attempted.
- EC2 instance allocation is high-confidence by unique Usage Type and observed instance types/hours, but the historical t3.large cannot be mapped to a current resource.
- The pricing API returned no matching regional products in this environment, so staging estimates use observed eu-west-2 rates where available and standard eu-west-2 on-demand configuration rates; allow a small invoice variance.
- Tax is not allocated to environments and savings may change future tax separately.

## Explicit no-change attestation

No EC2 stop/terminate, RDS stop/delete, ECS desired-count change, ALB/VPC Endpoint/EIP/EBS mutation, Terraform command, Secret value operation, database connection, GitHub push, or any other AWS write was performed.
