# Production low-traffic Terraform plan review

State: `cloud-a/prod/terraform.tfstate`. Saved plan: `environment/production-low-traffic.tfplan`, SHA-256 `80b77e467b8994bd93dd0c7c1abcd5998410413e08eff21441bccc490cf70923`. Apply was not run.

## Actions

| Action | Count |
|---|---:|
| add | 4 |
| change | 2 |
| replace | **0** |
| destroy | **0** |

Adds: `module.ecs.aws_ecs_task_definition.app_low_traffic[0]` (256/512 separate rollback-safe family), autoscaling target min 1/max 2, CPU target policy 60%, memory target policy 70%.

Changes: `module.ecs.aws_ecs_service.app` points to the new task definition and enables deployment circuit-breaker rollback; `module.database.aws_db_instance.main` changes only `instance_class: db.t4g.medium -> db.t4g.small` in place.

JSON shows zero action for Production VPC, subnets, NAT/EIP/routes, ALB/listener/target/SG, ECS cluster/current task definition, ECR, artifact S3, IAM, Secrets, DB storage/subnet/SG, and state. RDS replace is zero; resource destroy is zero. Multi-AZ, 50 GiB gp2, backup retention, encryption, private access and deletion protection remain unchanged.

The current task definition stays registered and Terraform-managed, providing direct rollback. Rolling minimum/maximum remain 100/200, health grace remains 60 seconds, and circuit breaker rollback becomes enabled.

## Apply blockers

The configuration and plan are ready for review, but apply is prohibited in this turn. Before approval: create/verify a Production manual snapshot, confirm a valid PITR window (EarliestRestorableTime was null), accept the Multi-AZ class-change failover/restart window, add required alarms or explicitly accept the current no-alarm risk, verify target health, and recheck the exact saved-plan checksum.

Decision: `READY_FOR_PRODUCTION_100RPM_DOWNSIZING_APPLY_APPROVAL` means ready to request those human approvals; it does not authorize apply.
