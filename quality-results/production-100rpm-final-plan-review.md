# Production 100 RPM remediated final plan review

Plan: `environment/production-100rpm-pitr-remediated-final.tfplan`
SHA-256: `6c4a977c54942c734526abc7f233124014a74eef861fc298f91f90b28b27efc3`

Actions: add 19, change 3, replace 0, destroy 0. Adds are one 256/512 low-traffic task definition, autoscaling target/two policies, 13 alarms, the dedicated `ai-platform-prod-alerts` topic, and an email subscription for `info@nagi-neco.com`. The subscription does not auto-confirm. Updates are the RDS class in place, ECS service task definition/circuit breaker, and ECS cluster Container Insights.

RDS changes only from `db.t4g.medium` to `db.t4g.small`; Multi-AZ, 50 GiB gp2, 14-day retention, deletion protection and encryption remain. `apply_immediately=false` and `sat:02:43-sat:03:13` remain. ALB, NAT, VPC, S3, ECR, IAM, Secrets and state have no destructive action. RDS replacement, all replacement, Production infrastructure destroy and Staging actions are zero. The image remains `ai-platform-prod:v4`; desired/min/max are 1/1/2.

Snapshot `ai-platform-prod-pre-100rpm-downsize-20260812-010957` is available, 100% and encrypted. Automated backup is active with matching `DbiResourceId`, matching 14-day retention, zero recent failure events, and restore window `2026-08-01T13:20:41.375000+00:00` through `2026-08-12T10:37:31+00:00`. The latest automated snapshot is available and encrypted. The DB-instance Earliest field is null and recorded as `PITR_API_FIELD_WARNING`; the complete automated-backup restore window satisfies the required PITR gate.

The old `production-100rpm-remediated-final.tfplan` (`d6f094d...5df0`), `production-100rpm-final.tfplan` (`98fd4a2...bd39`), and `production-low-traffic.tfplan` are **STALE / INVALID** and must never be applied. This new PITR-remediated plan was generated from the latest `cloud-a/prod/terraform.tfstate` for review only and was not applied. After an explicitly approved apply, a human must confirm the SNS email before notifications become operational.

Cost remains approximately $192/month before change and $134/month for the capacity baseline. Thirteen standard alarms add roughly $1.30/month before any free-tier benefit; SNS email is usage based and negligible at expected alarm volume, while Container Insights is usage-variable. Use approximately $135–136/month as a monitored low-traffic estimate, $56–57/month Production saving, and $262–265/month combined with the existing Staging saving.
