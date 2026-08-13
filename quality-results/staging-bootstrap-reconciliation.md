# Staging bootstrap reconciliation

Date: 2026-08-10 UTC
Implementation commit: `5a9aa3e`
AWS account / region: `557604519341` / `eu-west-2`
State: `system-navigator/staging/terraform.tfstate`

## Service Discovery root cause and fix

The shared backend/worker `aws_service_discovery_service` configuration contained an empty `health_check_custom_config {}`. AWS and AWS provider 6.58.0 omitted that empty block during refresh, while Terraform treated adding it as ForceNew, producing two replacements after the successful bootstrap apply.

The existing services need DNS registration but do not need a custom health check before runtime ECS services exist. The empty block was removed. No `lifecycle.ignore_changes`, state removal, import, taint, resource deletion, or apply was used. A safety test requires the backend/worker set, stable DNS configuration, absence of the empty custom-health block, and absence of `ignore_changes`.

Four Terraform roots validate and 17 staging Terraform safety tests pass. The ignored saved plan `environment/staging/staging-bootstrap-reconcile.tfplan` and its ignored text rendering report `No changes`:

| Action | Count |
|---|---:|
| Add | 0 |
| Change | 0 |
| Replace | 0 |
| Destroy | 0 |

Backend discovery action is `no-op`; worker discovery action is `no-op`. RDS, VPC, ALB, task definitions, IAM, S3, and production have no planned action. The reconcile plan was not applied because no changes exist and apply was prohibited.

## RDS PITR read-only result

RDS identifier `system-navigator-staging-db` is available with backup retention 3 and deletion protection enabled. `LatestRestorableTime` is `2026-08-10T14:16:14Z`; `EarliestRestorableTime` remains null. The automated-backup status is `active`, but both restore-window timestamps returned null. `RDS_PITR_PROTECTION` remains `BLOCKED` until concrete earliest and latest timestamps are available. A separately approved manual snapshot remains mandatory before migration and was not created here.

The application DB Secret container exists with zero versions. No Secret value was retrieved or set. Runtime ECS services and running tasks remain zero. SNS email remains `PendingConfirmation`. No DB connection, migration, runtime-service action, Terraform apply, GitHub push, or production change occurred.

Decision: `WAITING_FOR_RDS_PITR_PROTECTION`.
