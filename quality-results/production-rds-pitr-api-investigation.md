# Production RDS PITR API investigation

Date: 2026-08-12 UTC
Mode: read-only; no AWS or Terraform changes

## Finding

Classification: `DB_INSTANCE_API_DELAY_OR_FIELD_INCONSISTENCY`.

`DescribeDBInstances` returns a null `EarliestRestorableTime`, while the matching current automated-backup record exposes a valid restore window. All independent protection indicators agree: the DB is available, retention is 14 days, the immutable DB resource IDs and creation times match, automated-backup status is active, twelve encrypted automated snapshots are available, and every backup event in the last seven days completed without a failure event.

The available evidence does not identify a recent configuration change or a protection failure. The narrowest supported explanation is a response-field inconsistency in the DB Instance representation, not missing automated backups. This investigation cannot distinguish an AWS control-plane display delay from another service-side omission without AWS Support.

## DB instance and automated backup

| Field | DB instance | Automated backup |
|---|---|---|
| Identifier | `ai-platform-prod-postgres` | `ai-platform-prod-postgres` |
| DbiResourceId | `db-HLY4EEXCG4CVJNEV2G44AK2IUY` | `db-HLY4EEXCG4CVJNEV2G44AK2IUY` |
| Create time | `2026-08-01T13:11:28.986Z` | `2026-08-01T13:11:28Z` |
| Status | `available` | `active` |
| Backup retention | 14 days | 14 days |
| Backup window | `23:00-23:30` | — |
| Earliest | null | `2026-08-01T13:20:41.375Z` |
| Latest | `2026-08-12T04:02:27Z` | `2026-08-12T04:02:27Z` |

Resource identity and retention match. The automated restore interval is ordered (`Earliest < Latest`) and its latest point was about six minutes behind the `2026-08-12T04:08:53Z` observation time, consistent with an advancing transaction-log restore window.

## Snapshot and event inventory

- Automated snapshot count: 12.
- Latest: `rds:ai-platform-prod-postgres-2026-08-11-23-10`.
- Latest snapshot time: `2026-08-11T23:10:13.834Z`.
- Latest status/encryption: `available` / encrypted.
- The inventory spans `2026-08-01T13:20:41.375Z` through `2026-08-11T23:10:13.834Z`; all 12 are available and encrypted.
- Seven-day events contain successful `Backing up DB instance` / `Finished DB Instance backup` pairs for August 5–12.
- Backup failure events: none observed.
- Other relevant event: a system update was announced on August 5; there was no observed failover, reboot, restore, or backup failure.

CloudTrail lookup for `ModifyDBInstance`, `RestoreDBInstanceToPointInTime`, and `DeleteDBInstance` over August 1–12 found no event targeting `ai-platform-prod-postgres`. Returned events concerned Staging resources. There is therefore no observed recent Production retention change from 0 to 14, restore, or deletion. CloudTrail event-history coverage and lookup filters are finite, so absence is evidence for the inspected period, not a lifetime guarantee.

## API semantics and Gate recommendation

AWS documents `DBInstanceAutomatedBackup.RestoreWindow` as the earliest and latest time to which a DB instance can be restored, and documents `active` as automated backups for a current instance. The restore command accepts a source identifier plus either an explicit UTC `RestoreTime` or `UseLatestRestorableTime`; it creates a new target DB. No restore command was executed.

Recommended human-approved PITR Gate:

1. Automated backup status is `active`.
2. Its DbiResourceId equals the available source DB's DbiResourceId.
3. RestoreWindow Earliest and Latest are both non-null and Earliest is earlier than Latest.
4. Instance and automated-backup retention are equal and greater than zero.
5. Recent encrypted automated snapshots are available and backup events have no failure.
6. The pre-change manual snapshot is available and encrypted.

The current system satisfies these conditions, including the retained manual snapshot `ai-platform-prod-pre-100rpm-downsize-20260812-010957`. It is reasonable to let a human replace the overly strict DB-instance-field conjunction with this corroborated Gate. Codex did not change the Gate.

## Remaining risk

The APIs and snapshot inventory provide strong evidence that PITR protection exists, but do not prove that a restore job completes and the restored database is usable. A separately approved temporary PITR restore test is recommended for maximum Production recovery assurance, followed by approved cleanup. It is not necessary to explain the null field and was not performed here. AWS Support can also investigate why this DB's `DescribeDBInstances.EarliestRestorableTime` is omitted.

The saved downsizing plan remains unchanged and unapplied: `production-100rpm-remediated-final.tfplan`, SHA-256 `d6f094ded385f70628f9e0840e86c051fc2308d78a6afc313d5aafe32e8a5df0`.

Official references:

- AWS CLI `describe-db-instance-automated-backups`: https://docs.aws.amazon.com/cli/latest/reference/rds/describe-db-instance-automated-backups.html
- RDS API `DBInstanceAutomatedBackup`: https://docs.aws.amazon.com/AmazonRDS/latest/APIReference/API_DBInstanceAutomatedBackup.html
- AWS CLI `restore-db-instance-to-point-in-time`: https://docs.aws.amazon.com/cli/latest/reference/rds/restore-db-instance-to-point-in-time.html
