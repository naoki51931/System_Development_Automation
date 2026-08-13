from copy import deepcopy

import pytest

from scripts.production_pitr_gate import evaluate_pitr_gate


@pytest.fixture
def evidence():
    return {
        "db_instance": {
            "DbiResourceId": "db-EXAMPLE",
            "BackupRetentionPeriod": 14,
            "EarliestRestorableTime": "2026-08-01T00:00:00Z",
            "LatestRestorableTime": "2026-08-12T00:00:00Z",
        },
        "automated_backup": {
            "Status": "active",
            "DbiResourceId": "db-EXAMPLE",
            "BackupRetentionPeriod": 14,
            "RestoreWindow": {
                "EarliestTime": "2026-08-01T00:00:00Z",
                "LatestTime": "2026-08-12T00:00:00Z",
            },
        },
        "automated_snapshots": [
            {
                "Status": "available",
                "Encrypted": True,
                "SnapshotCreateTime": "2026-08-11T23:00:00Z",
            }
        ],
        "manual_snapshot": {"Status": "available", "Encrypted": True},
        "recent_backup_failures": [],
    }


def test_valid_automated_backup_evidence_passes(evidence):
    assert evaluate_pitr_gate(evidence)["pass"] is True


def test_db_instance_earliest_null_is_warning_only(evidence):
    evidence["db_instance"]["EarliestRestorableTime"] = None
    result = evaluate_pitr_gate(evidence)
    assert result["pass"] is True
    assert result["warnings"] == [
        "PITR_API_FIELD_WARNING: DBInstance.EarliestRestorableTime is null"
    ]


@pytest.mark.parametrize(
    ("mutate", "failure"),
    [
        (
            lambda e: e["automated_backup"].update(Status="retained"),
            "AUTOMATED_BACKUP_NOT_ACTIVE",
        ),
        (
            lambda e: e["automated_backup"].update(DbiResourceId="db-OTHER"),
            "AUTOMATED_BACKUP_RESOURCE_ID_MISMATCH",
        ),
        (
            lambda e: e["automated_backup"].update(BackupRetentionPeriod=0),
            "AUTOMATED_BACKUP_RETENTION_INVALID",
        ),
        (
            lambda e: e["automated_backup"].update(BackupRetentionPeriod=7),
            "BACKUP_RETENTION_MISMATCH",
        ),
        (
            lambda e: e["automated_backup"]["RestoreWindow"].update(EarliestTime=None),
            "AUTOMATED_RESTORE_WINDOW_EARLIEST_MISSING",
        ),
        (
            lambda e: e["automated_backup"]["RestoreWindow"].update(LatestTime=None),
            "AUTOMATED_RESTORE_WINDOW_LATEST_MISSING",
        ),
        (
            lambda e: e["automated_backup"]["RestoreWindow"].update(
                EarliestTime="2026-08-12T00:00:00Z"
            ),
            "AUTOMATED_RESTORE_WINDOW_ORDER_INVALID",
        ),
        (lambda e: e.update(automated_snapshots=[]), "AUTOMATED_SNAPSHOT_MISSING"),
        (
            lambda e: e["automated_snapshots"][0].update(Status="creating"),
            "LATEST_AUTOMATED_SNAPSHOT_UNAVAILABLE",
        ),
        (
            lambda e: e["automated_snapshots"][0].update(Encrypted=False),
            "LATEST_AUTOMATED_SNAPSHOT_UNENCRYPTED",
        ),
        (
            lambda e: e.update(recent_backup_failures=[{"Message": "Backup failed"}]),
            "RECENT_BACKUP_FAILURE_OBSERVED",
        ),
        (
            lambda e: e["manual_snapshot"].update(Status="creating"),
            "MANUAL_SNAPSHOT_UNAVAILABLE",
        ),
        (
            lambda e: e["manual_snapshot"].update(Encrypted=False),
            "MANUAL_SNAPSHOT_UNENCRYPTED",
        ),
    ],
)
def test_gate_fails_closed(evidence, mutate, failure):
    candidate = deepcopy(evidence)
    mutate(candidate)
    result = evaluate_pitr_gate(candidate)
    assert result["pass"] is False
    assert failure in result["failures"]


def test_optional_restore_drill_is_not_a_required_gate(evidence):
    result = evaluate_pitr_gate(evidence)
    assert result["optional_test"] == "OPTIONAL_HIGH_ASSURANCE_DR_TEST"
    assert result["pass"] is True
