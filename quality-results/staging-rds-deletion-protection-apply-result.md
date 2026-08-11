# Staging RDS deletion protection apply result

Collected on 2026-08-11 for the separately approved pre-IDLE deletion-protection phase. The reviewed saved plan was applied exactly once. No new plan was substituted for the apply.

## Execution identity and scope

| Field | Value |
|---|---|
| Git HEAD before apply | `734c26da5c45877e3e2a19cf8a9ba0a40cbb90b8` |
| AWS account | `557604519341` |
| Region | `eu-west-2` |
| Terraform state key | `system-navigator/staging/terraform.tfstate` |
| Applied plan | `environment/staging/staging-rds-disable-deletion-protection.tfplan` |
| Plan SHA-256 | `f8b51360ebfc73939b2728e5545195e77e1bb85cb78047c55ceaa54735dace9d` |
| Reviewed actions | 0 add, 1 change, 0 replace, 0 destroy |
| Reviewed changed resource | `module.database.aws_db_instance.main[0]` |
| Reviewed changed key | `deletion_protection` only |

Immediately before apply, the saved plan was decoded again. It contained exactly one in-place resource action and changed `deletion_protection: true -> false`; all other reviewed RDS attributes were identical. The source RDS, snapshot, runtime, account, region, clean worktree, and Staging backend checks all passed.

## Apply result

The exact saved plan was applied with `terraform apply -input=false staging-rds-disable-deletion-protection.tfplan`. Terraform submitted an in-place modification for RDS physical ID `db-Y6SKIICUPWBUOBRZ4MLZJE23AY`. AWS returned the instance to `available`; Terraform state records `deletion_protection = false`.

| RDS field | Before | After | Result |
|---|---|---|---|
| Identifier | `system-navigator-staging-db` | same | PASS |
| Status | `available` | `available` | PASS |
| Deletion protection | `true` | `false` | PASS |
| Instance class | `db.t4g.small` | same | PASS |
| Storage | 20 GiB gp3 | same | PASS |
| Multi-AZ | `false` | same | PASS |
| Engine | PostgreSQL 17.9 | same | PASS |
| Backup retention | 3 days | same | PASS |
| Public access | `false` | same | PASS |
| Storage encryption | `true` | same | PASS |
| DB subnet group | `system-navigator-staging-db` | same | PASS |
| Security group | `sg-0d809b8aac1d6bbac` | same | PASS |

## Retained safeguards and post-checks

| Check | Result |
|---|---|
| Manual snapshot `system-navigator-staging-pre-idle-20260811-013548` | `available`, encrypted, retained |
| ECS runtime services | 0 |
| Running ECS tasks, including migration | 0 |
| Production resource actions | 0 |
| Secret operations | none |
| DB connections | none |
| Migrations | none |
| RDS/ALB/Endpoint deletion | none |
| IDLE-mode plan/apply | not performed |

The post-apply plan used the same active-mode deletion-approval inputs as the saved plan: `allow_database_deletion=true`, the existing removal approval, and the retained snapshot identifier. It returned exit code 0 and `No changes. Your infrastructure matches the configuration.`

## Gate and next approval

| Gate | Result |
|---|---|
| SAVED_PLAN_APPLIED | PASS |
| RDS_STILL_EXISTS | PASS |
| RDS_AVAILABLE | PASS |
| DELETION_PROTECTION_DISABLED | PASS |
| RDS_CLASS_UNCHANGED | PASS |
| RDS_STORAGE_UNCHANGED | PASS |
| RDS_ENGINE_UNCHANGED | PASS |
| RDS_BACKUP_UNCHANGED | PASS |
| RDS_PRIVATE | PASS |
| RDS_ENCRYPTED | PASS |
| MANUAL_SNAPSHOT_AVAILABLE | PASS |
| MANUAL_SNAPSHOT_ENCRYPTED | PASS |
| RUNTIME_SERVICES_ZERO | PASS |
| PRODUCTION_CHANGES_ZERO | PASS |
| POST_APPLY_PLAN_CLEAN | PASS |

`READY_FOR_FINAL_STAGING_IDLE_PLAN_APPROVAL`

The next separately approved phase must create a **fresh** IDLE-mode plan from the current state, recheck the retained snapshot, and review every destroy action. The old IDLE plan must not be used. This apply does not authorize RDS deletion, IDLE apply, ALB/Endpoint deletion, snapshot deletion, Secret/DB access, migration, or Production changes.
