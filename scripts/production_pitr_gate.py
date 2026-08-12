#!/usr/bin/env python3
"""Fail-closed Production RDS PITR preflight using read-only AWS APIs."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import subprocess
from typing import Any


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def evaluate_pitr_gate(evidence: dict[str, Any]) -> dict[str, Any]:
    instance = evidence.get("db_instance") or {}
    backup = evidence.get("automated_backup") or {}
    restore = backup.get("RestoreWindow") or {}
    snapshots = evidence.get("automated_snapshots") or []
    manual = evidence.get("manual_snapshot") or {}
    failures = evidence.get("recent_backup_failures") or []
    failures_found: list[str] = []
    warnings: list[str] = []

    if backup.get("Status") != "active":
        failures_found.append("AUTOMATED_BACKUP_NOT_ACTIVE")
    if not instance.get("DbiResourceId") or backup.get("DbiResourceId") != instance.get(
        "DbiResourceId"
    ):
        failures_found.append("AUTOMATED_BACKUP_RESOURCE_ID_MISMATCH")

    instance_retention = instance.get("BackupRetentionPeriod")
    backup_retention = backup.get("BackupRetentionPeriod")
    if not isinstance(backup_retention, int) or backup_retention <= 0:
        failures_found.append("AUTOMATED_BACKUP_RETENTION_INVALID")
    if backup_retention != instance_retention:
        failures_found.append("BACKUP_RETENTION_MISMATCH")

    earliest = restore.get("EarliestTime")
    latest = restore.get("LatestTime")
    if not earliest:
        failures_found.append("AUTOMATED_RESTORE_WINDOW_EARLIEST_MISSING")
    if not latest:
        failures_found.append("AUTOMATED_RESTORE_WINDOW_LATEST_MISSING")
    if earliest and latest:
        try:
            if _timestamp(earliest) >= _timestamp(latest):
                failures_found.append("AUTOMATED_RESTORE_WINDOW_ORDER_INVALID")
        except ValueError:
            failures_found.append("AUTOMATED_RESTORE_WINDOW_TIMESTAMP_INVALID")

    if not snapshots:
        failures_found.append("AUTOMATED_SNAPSHOT_MISSING")
    else:
        latest_snapshot = max(
            snapshots, key=lambda item: item.get("SnapshotCreateTime", "")
        )
        if latest_snapshot.get("Status") != "available":
            failures_found.append("LATEST_AUTOMATED_SNAPSHOT_UNAVAILABLE")
        if latest_snapshot.get("Encrypted") is not True:
            failures_found.append("LATEST_AUTOMATED_SNAPSHOT_UNENCRYPTED")

    if failures:
        failures_found.append("RECENT_BACKUP_FAILURE_OBSERVED")
    if manual.get("Status") != "available":
        failures_found.append("MANUAL_SNAPSHOT_UNAVAILABLE")
    if manual.get("Encrypted") is not True:
        failures_found.append("MANUAL_SNAPSHOT_UNENCRYPTED")

    if instance.get("EarliestRestorableTime") is None:
        warnings.append(
            "PITR_API_FIELD_WARNING: DBInstance.EarliestRestorableTime is null"
        )

    return {
        "pass": not failures_found,
        "status": "PASS" if not failures_found else "FAIL",
        "failures": failures_found,
        "warnings": warnings,
        "optional_test": "OPTIONAL_HIGH_ASSURANCE_DR_TEST",
    }


def _aws(*args: str) -> Any:
    result = subprocess.run(
        ["aws", *args, "--output", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def collect_evidence(
    db_identifier: str, manual_snapshot: str, region: str
) -> dict[str, Any]:
    instances = _aws(
        "rds",
        "describe-db-instances",
        "--db-instance-identifier",
        db_identifier,
        "--region",
        region,
    )["DBInstances"]
    backups = _aws(
        "rds",
        "describe-db-instance-automated-backups",
        "--db-instance-identifier",
        db_identifier,
        "--region",
        region,
    )["DBInstanceAutomatedBackups"]
    snapshots = _aws(
        "rds",
        "describe-db-snapshots",
        "--db-instance-identifier",
        db_identifier,
        "--snapshot-type",
        "automated",
        "--region",
        region,
    )["DBSnapshots"]
    manual_snapshots = _aws(
        "rds",
        "describe-db-snapshots",
        "--db-snapshot-identifier",
        manual_snapshot,
        "--region",
        region,
    )["DBSnapshots"]
    events = _aws(
        "rds",
        "describe-events",
        "--source-identifier",
        db_identifier,
        "--source-type",
        "db-instance",
        "--duration",
        "10080",
        "--region",
        region,
    )["Events"]
    failure_events = [
        {"Date": event.get("Date"), "Message": event.get("Message")}
        for event in events
        if any(
            word in event.get("Message", "").lower()
            for word in ("backup failed", "snapshot failed")
        )
    ]
    if len(instances) != 1 or len(backups) != 1 or len(manual_snapshots) != 1:
        raise RuntimeError(
            "PITR evidence lookup did not return exactly one required resource"
        )
    return {
        "db_instance": instances[0],
        "automated_backup": backups[0],
        "automated_snapshots": snapshots,
        "manual_snapshot": manual_snapshots[0],
        "recent_backup_failures": failure_events,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-identifier", required=True)
    parser.add_argument("--manual-snapshot", required=True)
    parser.add_argument("--region", required=True)
    args = parser.parse_args()
    evidence = collect_evidence(args.db_identifier, args.manual_snapshot, args.region)
    result = evaluate_pitr_gate(evidence)
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
