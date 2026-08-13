# Production 100 RPM residual plan review

Plan: `environment/production-100rpm-residual.tfplan`

SHA-256: `992ec5ffb8ec5da4383b29c23e908689db7f4339bb4eccc71f18f0dc3bbc5578`

Actions: **6 add / 1 change / 0 replace / 0 destroy**. ECS, autoscaling, ALB/ECS alarms, ALB, NAT and Staging actions are zero.

The only update is in-place RDS class `db.t4g.medium` → `db.t4g.small`. Multi-AZ, 50 GiB gp2, PostgreSQL 18.3, retention 14, deletion protection, encryption, private access, subnet group and security group remain unchanged. `apply_immediately=false` and maintenance window `sat:02:43-sat:03:13` remain. Replacement is zero.

The six additions are RDS alarms for `CPUUtilization`, `DatabaseConnections`, `FreeableMemory`, `FreeStorageSpace`, `ReadLatency`, and `WriteLatency`. Every alarm dimension is `DBInstanceIdentifier=ai-platform-prod-postgres`; alarm and OK actions both point to `arn:aws:sns:eu-west-2:557604519341:ai-platform-prod-alerts`. No Staging resource or SNS is referenced.

The plan was generated from the latest `cloud-a/prod/terraform.tfstate` after confirming the state contains the low-traffic task definition, ECS service, autoscaling target/policies, seven existing alarms, SNS topic and subscription. This is review-only. Terraform apply was not executed.

Capacity classification is `CLASS_SUPPORTED_CAPACITY_TEMPORARILY_UNAVAILABLE`, and the recommendation is `RETRY_SAME_CLASS_RECOMMENDED`. Final gate: **READY_FOR_PRODUCTION_RDS_SMALL_RETRY_APPLY_APPROVAL**. A separate human approval must name this exact plan SHA before any apply.
