# Staging RDS pre-IDLE snapshot and restore test

Collected on 2026-08-11 for the Staging-only RDS safety gate. No database connection, Secret read/write, migration, Terraform apply, RDS modification/deletion, or Production change was performed.

## Execution identity

| Field | Value |
|---|---|
| AWS account | `557604519341` |
| Region | `eu-west-2` |
| Git HEAD before execution | `56e8494bc7182b3a9c19a329cfc55c432755cd92` |
| Source RDS | `system-navigator-staging-db` |
| Source status after test | `available` |
| Source class | `db.t4g.small` |
| Source deletion protection | `true` |
| Source backup retention | 3 days |
| Runtime ECS services | 0 |
| Runtime/migration running tasks | 0 |

The preflight Terraform plan used the active/bootstrap tfvars. It reported `0 to add, 0 to change, 0 to destroy`. Its detailed exit code was 2 only because the IDLE-mode implementation adds moved state addresses and two output values; it proposed no AWS infrastructure change. No plan was applied.

## Manual snapshot

| Field | Value |
|---|---|
| Snapshot ID | `system-navigator-staging-pre-idle-20260811-013548` |
| Snapshot ARN | `arn:aws:rds:eu-west-2:557604519341:snapshot:system-navigator-staging-pre-idle-20260811-013548` |
| Source DB | `system-navigator-staging-db` |
| Status | `available` |
| Progress | 100% |
| Type | `manual` |
| Engine | PostgreSQL 17.9 |
| Storage | 20 GiB gp3 |
| Encrypted | `true` |
| Snapshot creation time | `2026-08-11T01:36:02.031000+00:00` |

## Restore test

The snapshot was restored outside Terraform under a distinct Staging-only identifier. The existing Staging database was not replaced or modified.

| Field | Value |
|---|---|
| Restore identifier | `system-navigator-staging-restore-test` |
| Restore ARN | `arn:aws:rds:eu-west-2:557604519341:db:system-navigator-staging-restore-test` |
| Status | `available` |
| Instance class | `db.t4g.micro` |
| Engine | PostgreSQL 17.9 |
| Storage | 20 GiB gp3 |
| Multi-AZ | `false` |
| Publicly accessible | `false` |
| Encrypted | `true` |
| VPC | `vpc-0b5ce4ab333cc5b7c` |
| DB subnet group | `system-navigator-staging-db` |
| Subnets | `subnet-04f53eb66448ec0ea`, `subnet-02a9ba85decdf2ca2` |
| Security group | `sg-0d809b8aac1d6bbac` |
| Instance creation time | `2026-08-11T01:43:16.996000+00:00` |

No credentials were supplied or retrieved. Success is limited to snapshot restore, RDS availability, and infrastructure configuration. Schema and row validation require separate approval for DB access.

## Gate result

| Gate | Result |
|---|---|
| SOURCE_RDS_UNCHANGED | PASS |
| RUNTIME_SERVICES_ZERO | PASS |
| MANUAL_SNAPSHOT_CREATED | PASS |
| MANUAL_SNAPSHOT_AVAILABLE | PASS |
| MANUAL_SNAPSHOT_ENCRYPTED | PASS |
| RESTORE_TEST_CREATED | PASS |
| RESTORE_TEST_AVAILABLE | PASS |
| RESTORE_TEST_PRIVATE | PASS |
| RESTORE_TEST_ENCRYPTED | PASS |
| RESTORE_TEST_CORRECT_VPC | PASS |
| PRODUCTION_CHANGES_ZERO | PASS |
| SECRET_UNTOUCHED | PASS |
| MIGRATION_NOT_RUN | PASS |
| IDLE_PLAN_NOT_APPLIED | PASS |

`RDS_RESTORE_TEST = PASS`

`READY_FOR_STAGING_RESTORE_TEST_CLEANUP_APPROVAL`

## Required follow-up approvals

`RESTORE_TEST_CLEANUP_REQUIRED`: the temporary `system-navigator-staging-restore-test` instance remains running and incurs RDS compute/storage charges until a separate human approval authorizes deletion. This work did not delete it.

After cleanup is separately reviewed, the RDS deletion-protection change and a fresh final IDLE plan must each receive their own review and approval. The existing IDLE plan (`1 add, 1 change, 0 replace, 35 destroy`) was not applied. Source RDS deletion and IDLE-mode apply remain prohibited.
