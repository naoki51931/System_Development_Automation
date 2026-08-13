# Staging RDS deletion protection plan review

Collected on 2026-08-11 for the separate pre-IDLE deletion-protection phase. This is a plan-only review. No Terraform apply or AWS resource mutation was performed.

## Context

| Field | Value |
|---|---|
| Git HEAD at start | `ab6a2d268d934f83127a67c98e821cee8b716abd` |
| AWS account | `557604519341` |
| Region | `eu-west-2` |
| Source RDS | `system-navigator-staging-db` |
| Source status | `available` |
| Current deletion protection | `true` |
| Manual snapshot | `system-navigator-staging-pre-idle-20260811-013548` |
| Snapshot status | `available` |
| Snapshot encrypted | `true` |
| Restore test | PASS; temporary restore DB cleaned up |
| ECS services | 0 |
| Running ECS tasks | 0 |

## Safety design

`allow_database_deletion` is a Staging-only variable with default `false`. Disabling deletion protection requires all of the following plan inputs:

- `staging_mode="active"`, so the RDS remains present and the IDLE destroy set is excluded;
- `allow_database_deletion=true`, the dedicated phase approval;
- `idle_database_removal_approved=true`, the existing removal approval;
- the retained manual snapshot identifier, verified by the AWS data lookup as `available`.

The effective module input is `deletion_protection = var.deletion_protection && !var.allow_database_deletion`. Routine active and idle configuration leaves the new approval false. Production Terraform has no `allow_database_deletion` reference.

## Saved plan

| Field | Value |
|---|---|
| Binary plan | `environment/staging/staging-rds-disable-deletion-protection.tfplan` (ignored, not committed) |
| Text review | `environment/staging/staging-rds-disable-deletion-protection-plan.txt` (ignored, not committed) |
| Add | 0 |
| Change | 1 |
| Replace | 0 |
| Destroy | 0 |
| Resource | `module.database.aws_db_instance.main[0]` / `system-navigator-staging-db` |
| Action | in-place update |
| Changed attribute | `deletion_protection: true -> false` |

JSON comparison found exactly one actionable resource and exactly one changed key: `deletion_protection`. The following RDS properties are identical before and after: identifier, `db.t4g.small`, 20 GiB, gp3, Single-AZ, PostgreSQL engine/version configuration, DB subnet group, security group, three-day backup retention, private access, and encryption.

The plan also displays existing Terraform `moved` declarations and the two IDLE-mode outputs that are not yet stored in state. They have no AWS resource action. ALB, VPC Endpoints, S3, ECR, IAM, SNS, Budget, alarms, task definitions, security groups, and Production all have zero action.

## Validation

- `terraform fmt -recursive -check`: PASS.
- `terraform init -backend=false` and `terraform validate`: PASS for `bootstrap`, `environment`, `environment/staging`, and `environment/staging-prerequisites`.
- Staging Terraform safety tests: 20 passed. The only warning was the expected read-only pytest cache warning.
- Manual snapshot: still available and encrypted at plan time.
- Runtime services/tasks: still zero at plan time.
- Production impact: zero.

## Approval boundary and sequence

This saved plan was **not applied**. Applying it requires separate human approval and must use only the reviewed saved plan.

1. Phase A: separately approve and apply only the saved deletion-protection plan.
2. Phase B: verify through AWS that source RDS deletion protection is false.
3. Phase C: recheck that the retained manual snapshot is available and encrypted.
4. Phase D: create a fresh final IDLE-mode plan.
5. Phase E: review every destroy action again.
6. Phase F: obtain a separate human approval before any IDLE-mode apply.

`READY_FOR_STAGING_RDS_DELETION_PROTECTION_APPLY_APPROVAL`

This decision does not authorize apply, RDS deletion, snapshot deletion, DB/Secret access, migration, ALB or Endpoint deletion, IDLE apply, or Production changes.
