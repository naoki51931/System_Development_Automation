# Staging Idle state convergence

- Date: 2026-08-12 UTC
- Starting Git HEAD: `52e618998d3dc34c4d4e9cdc5260af87a49651ea`
- AWS account / region: `557604519341` / `eu-west-2`
- State key: `system-navigator/staging/terraform.tfstate`
- AWS changes: none
- Terraform apply/state mutations: none

## Local desired state

The ignored `environment/staging/terraform.tfvars` previously omitted `staging_mode`, so the declared default resolved to `active`. It now explicitly declares `staging_mode="idle"`, `enable_runtime_services=false`, `allow_staging_reactivation=false`, `allow_database_deletion=false`, `restore_db_from_snapshot=false`, and an empty active-restore snapshot identifier. The already-applied Idle gate retains its approved manual snapshot input so the local declaration exactly matches remote state.

An ACTIVE hard gate was added: `staging_mode="active"` is invalid unless `allow_staging_reactivation=true` is explicitly supplied. A `terraform plan -refresh=false` negative test confirmed the plan fails with `ACTIVE_REACTIVATION blocked`. The flag authorizes planning only, not apply.

## Convergence and inventory

`staging-idle-convergence.tfplan` reports `No changes`: add 0, change 0, replace 0, destroy 0. The plan was not applied.

- RDS, staging ALB, Interface Endpoints, staging ECS cluster/services/tasks, Cloud Map, and Idle-target alarms are absent from state and AWS.
- Staging VPC is available; six subnets and the S3 Gateway endpoint are present.
- Artifact S3, two staging ECR repositories, DB Secret container, four log groups, IAM, SNS, Budget, DB subnet group/SG, state, and manual snapshot remain preserved.
- Snapshot `system-navigator-staging-pre-idle-20260811-013548` is available and encrypted.
- Production RDS is available, ECS is ACTIVE with one running task/service, and ALB is active. Production changes: zero.

Expected Idle cost remains approximately USD 2–4/month, with approximately USD 206–208/month removed by the absent RDS, ALB/Public IPv4, Interface Endpoints, and runtime ECS.

## Validation

- `terraform fmt -recursive -check`: PASS.
- `terraform init -backend=false` and `terraform validate`: PASS for `bootstrap`, `environment`, `environment/staging`, and `environment/staging-prerequisites`.
- `tests/test_staging_terraform.py`: 21 PASS using its dependency-free test functions (pytest was not installed in the environment).
- ACTIVE reactivation negative plan: PASS; explicit approval omission hard-fails.
- Idle refreshed plan: PASS, 0/0/0/0.

## Artifact validity and gates

`staging-final-idle.tfplan` and `staging-current-drift-review.tfplan` are INVALID/STALE and permanently prohibited from apply. `staging-idle-convergence.tfplan` and its plan text are ignored review artifacts and are also not apply authorizations.

- `AWS_IDLE_STATE_CONFIRMED=PASS`
- `LOCAL_STAGING_MODE_IDLE=PASS`
- `RDS_ABSENT=PASS`
- `ALB_ABSENT=PASS`
- `INTERFACE_ENDPOINTS_ABSENT=PASS`
- `RUNTIME_ECS_ABSENT=PASS`
- `PERSISTENT_RESOURCES_PRESERVED=PASS`
- `MANUAL_SNAPSHOT_PRESERVED=PASS`
- `PLAN_ADD_ZERO=PASS`
- `PLAN_CHANGE_ZERO=PASS`
- `PLAN_REPLACE_ZERO=PASS`
- `PLAN_DESTROY_ZERO=PASS`
- `PRODUCTION_CHANGES_ZERO=PASS`
- `TERRAFORM_VALIDATE=PASS`
- `TERRAFORM_TESTS=PASS`

Final decision: **STAGING_IDLE_MODE_CONVERGED** and **READY_FOR_PRODUCTION_SAFETY_REMEDIATION**. Any Production work still requires its own explicit scope, plan review, and approval.
