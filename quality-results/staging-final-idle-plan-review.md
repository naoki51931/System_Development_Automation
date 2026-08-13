# Final Staging IDLE plan review

Collected on 2026-08-11 from the current post-deletion-protection state. This is a plan-only review; `terraform apply` was not run.

## Identity and safety gate

| Field | Value |
|---|---|
| Git HEAD at start | `711fc1e1b202de3ad3de5465dd381323514901e9` |
| AWS account / Region | `557604519341` / `eu-west-2` |
| State key | `system-navigator/staging/terraform.tfstate` |
| Source RDS | `system-navigator-staging-db`: available, private, encrypted, deletion protection false |
| Manual snapshot | `system-navigator-staging-pre-idle-20260811-013548`: available, encrypted, correct source |
| Restore test / cleanup | PASS / complete |
| ECS services / running tasks | 0 / 0 |

The fresh plan used `staging_mode=idle`, `allow_database_deletion=true`, `idle_database_removal_approved=true`, the retained snapshot identifier, and runtime services false. The snapshot remains external recovery data and is not Terraform-managed or destroyed.

## Plan summary

| Action | Count |
|---|---:|
| add | 1 |
| change | 1 |
| replace | **0** |
| destroy | **35** |
| read action | 0 (the snapshot data source resolved during planning) |

Plan: `environment/staging/staging-final-idle.tfplan`; SHA-256 `b2c8ab750e3f939a6023d89df921bcb7fd78c5bd4891de1d1a260520f4f3ee1a`. The binary and text rendering are ignored and not committed.

Add: `terraform_data.idle_apply_gate[0]` records the explicit approval, snapshot ID, and AWS-verified available status; its provisioner fails closed if those inputs are absent.

Change: `module.ecs.aws_iam_role_policy.execution_secrets` updates only its policy to remove the disappearing RDS-managed master Secret ARN. Permission for the persistent application DB Secret container remains. This is directly caused by RDS removal and is not unrelated drift.

## Destroy classification — all 35 resources

| Category | Terraform address | AWS name/ID | IDLE reason |
|---|---|---|---|
| RDS | `module.database.aws_db_instance.main[0]` | `system-navigator-staging-db` | Remove DB compute/storage; manual snapshot retained |
| ECS | `module.ecs.aws_ecs_cluster.main[0]` | `system-navigator-staging-cluster` | No services/tasks; recreate in ACTIVE |
| Task Definition | `module.ecs.aws_ecs_task_definition.backend[0]` | backend | No idle runtime |
| Task Definition | `module.ecs.aws_ecs_task_definition.frontend[0]` | frontend | No idle runtime |
| Task Definition | `module.ecs.aws_ecs_task_definition.migration[0]` | migration | No idle migration |
| Task Definition | `module.ecs.aws_ecs_task_definition.worker[0]` | worker | No idle runtime |
| Other | `module.ecs.aws_iam_role_policy.migration[0]` | `database-secret-only` | Migration-only inline policy is unnecessary |
| ALB | `module.ecs.aws_lb.main[0]` | `system-navigator-staging-alb` | Remove fixed ALB/IPv4 cost |
| ALB listener/rule | `module.ecs.aws_lb_listener.http[0]` | HTTP listener | ALB dependency |
| ALB listener/rule | `module.ecs.aws_lb_listener_rule.backend_http[0]` | backend rule | Listener/target dependency |
| Target Group | `module.ecs.aws_lb_target_group.backend[0]` | `system-navigator-staging-be` | No backend/ALB |
| Target Group | `module.ecs.aws_lb_target_group.frontend[0]` | `system-navigator-staging-fe` | No frontend/ALB |
| Security Group | `module.ecs.aws_security_group.alb[0]` | `system-navigator-staging-alb` | ALB-dedicated SG |
| Cloud Map | `module.ecs.aws_service_discovery_private_dns_namespace.main[0]` | `staging.system-navigator.internal` | No discovery clients |
| Cloud Map | `module.ecs.aws_service_discovery_service.internal["backend"]` | backend | No backend service |
| Cloud Map | `module.ecs.aws_service_discovery_service.internal["worker"]` | worker | No worker service |
| Security Group rule | `module.ecs.aws_vpc_security_group_ingress_rule.backend_alb[0]` | backend-from-ALB | ALB removed |
| Security Group rule | `module.ecs.aws_vpc_security_group_ingress_rule.backend_internal[0]` | backend-internal | Runtime removed |
| Security Group rule | `module.ecs.aws_vpc_security_group_ingress_rule.frontend_alb[0]` | frontend-from-ALB | ALB removed |
| Monitoring | `module.monitoring.aws_cloudwatch_metric_alarm.alb_5xx[0]` | ALB 5xx | ALB removed |
| Monitoring | `module.monitoring.aws_cloudwatch_metric_alarm.alb_response_time[0]` | ALB latency | ALB removed |
| Monitoring | `module.monitoring.aws_cloudwatch_metric_alarm.rds_connections[0]` | RDS connections | RDS removed |
| Monitoring | `module.monitoring.aws_cloudwatch_metric_alarm.rds_cpu[0]` | RDS CPU | RDS removed |
| Monitoring | `module.monitoring.aws_cloudwatch_metric_alarm.rds_freeable_memory[0]` | RDS memory | RDS removed |
| Monitoring | `module.monitoring.aws_cloudwatch_metric_alarm.rds_storage[0]` | RDS storage | RDS removed |
| Monitoring | `module.monitoring.aws_cloudwatch_metric_alarm.unhealthy_targets[0]` | target 1 | Target group removed |
| Monitoring | `module.monitoring.aws_cloudwatch_metric_alarm.unhealthy_targets[1]` | target 2 | Target group removed |
| Endpoint SG | `module.network.aws_security_group.endpoints[0]` | `system-navigator-staging-endpoints` | Used only by removed endpoints |
| Interface Endpoint | `module.network.aws_vpc_endpoint.interface["ecr.api"]` | ECR API | No idle runtime |
| Interface Endpoint | `module.network.aws_vpc_endpoint.interface["ecr.dkr"]` | ECR DKR | No idle runtime |
| Interface Endpoint | `module.network.aws_vpc_endpoint.interface["kms"]` | KMS | No idle runtime |
| Interface Endpoint | `module.network.aws_vpc_endpoint.interface["logs"]` | Logs | No idle runtime |
| Interface Endpoint | `module.network.aws_vpc_endpoint.interface["monitoring"]` | Monitoring | No idle runtime |
| Interface Endpoint | `module.network.aws_vpc_endpoint.interface["secretsmanager"]` | Secrets Manager | Endpoint removed; Secret retained |
| Interface Endpoint | `module.network.aws_vpc_endpoint.interface["sts"]` | STS | No idle runtime |

Counts: RDS 1; ALB/listener/rule/target groups/ALB SG and ingress rules 9; endpoints 7 plus endpoint SG 1; ECS cluster/task definitions/Cloud Map 8; monitoring 8; migration inline policy 1. Runtime ECS service destroys are zero because services already equal zero.

## Preserved resources and dependencies

Artifact S3, versioning, encryption, public-access block, TLS policy/lifecycle and `prevent_destroy` are no-op. The DB application Secret container is no-op; no Secret value is managed. VPC, six subnets, route tables/associations, Internet Gateway, task SG, DB SG, DB subnet group, and the free S3 Gateway Endpoint are no-op. Four log groups (`backend`, `worker`, `frontend`, `migration`) remain with 14-day retention; at current tiny/zero ingestion their expected cost is negligible, and reducing to seven days would save effectively zero.

ECR repositories, GitHub deploy role, SNS topic, and Budget live in the separate prerequisites state and have no action. The retained manual snapshot is outside Terraform and has no destroy action. JSON scanning found zero actionable Production reference (`ai-platform-prod`, `cloud-a/prod`, or `production`). Work EC2 `i-0add395a2d89805b5` is outside this plan; its separate ~$38/month stop candidate requires separate approval.

The ECS cluster itself has no material fixed fee, but current design removes it together with task definitions and Cloud Map for a clean runtime-free IDLE layer. The tradeoff is several minutes of ACTIVE reconstruction. Task definition revision history remains in AWS semantics even after Terraform deregistration.

Deleting the ALB removes its AWS DNS name. A later ACTIVE create receives a different DNS name; custom domain is disabled, so this is acceptable for temporary staging URLs.

## Cost and recovery

The 35 destroys match the measured cost drivers: seven two-AZ Interface Endpoints (~$127.75/month), RDS (~$54.9), and ALB/public IPv4 (~$26.62). Current fixed cost is about $210/month; retained ECR (~$0.14), application Secret (~$0.40), 20-GiB manual snapshot (~$1.9), and negligible S3/CloudWatch/request variance yield an estimated $2–4/month IDLE floor. Expected saving is ~$206–208/month.

ACTIVE recovery remains:

1. Set `staging_mode=active` with runtime services false and approved connectivity.
2. Recreate connectivity, ALB, ECS definitions and Cloud Map.
3. Restore RDS from the externally supplied snapshot identifier; never commit it.
4. Wait for RDS available.
5. Create/verify the application DB user and update the persistent Secret outside Terraform.
6. Confirm backup/PITR and schema/Alembic revision.
7. Run migration only after separate approval.
8. Enable runtime services in a later reviewed plan.
9. Verify health, targets, worker and smoke tests.

## Validation and apply stop conditions

Four Terraform roots passed fmt/init/validate. The 20 Staging Terraform safety tests passed; the only warning was read-only pytest cache. Plan replacement count is zero.

Immediately before any separately approved apply, stop unless: snapshot available/encrypted, restore evidence and cleanup remain valid, RDS deletion protection is false, ECS services/tasks/migration are zero, DB connection ownership is manually confirmed safe, plan checksum and 35-destroy scope are unchanged, and Production impact remains zero. This review did not apply the plan.

All final gates PASS. Decision: `READY_FOR_FINAL_STAGING_IDLE_APPLY_APPROVAL`.
