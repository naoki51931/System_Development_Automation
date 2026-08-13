from copy import deepcopy

import pytest

from scripts.verify_production_100rpm_post_maintenance import evaluate_post_maintenance


@pytest.fixture
def evidence():
    alarms = []
    for category, count in (("alb", 4), ("ecs", 3), ("rds", 6)):
        alarms.extend(
            {"name": f"{category}-{index}", "category": category, "state": "OK"}
            for index in range(count)
        )
    return {
        "rds": {
            "DBInstanceClass": "db.t4g.small",
            "DBInstanceStatus": "available",
            "PendingModifiedValues": {},
            "MultiAZ": True,
            "AllocatedStorage": 50,
            "StorageType": "gp2",
            "BackupRetentionPeriod": 14,
            "DeletionProtection": True,
            "StorageEncrypted": True,
            "PubliclyAccessible": False,
        },
        "pitr": {"pass": True, "warnings": ["PITR_API_FIELD_WARNING"]},
        "manual_snapshot": {"Status": "available", "Encrypted": True},
        "ecs_service": {
            "desiredCount": 1,
            "runningCount": 1,
            "pendingCount": 0,
            "rolloutState": "COMPLETED",
        },
        "task_definition": {"cpu": "256", "memory": "512"},
        "target_states": ["healthy"],
        "http_status": {"/": 200, "/health": 200, "/docs": 200},
        "alarms": alarms,
        "sns": {
            "topic": "ai-platform-prod-alerts",
            "endpoint": "info@nagi-neco.com",
            "status": "Confirmed",
        },
        "alb_state": "active",
        "nat_state": "available",
        "staging": {"rds": 0, "alb": 0, "interface_endpoints": 0, "runtime_ecs": 0},
    }


def test_complete_post_maintenance_state_passes(evidence):
    result = evaluate_post_maintenance(evidence)
    assert result["pass"] is True
    assert result["alarm_states"] == {"OK": 13}


def test_alarm_requires_review_without_blocking(evidence):
    evidence["alarms"][0]["state"] = "ALARM"
    result = evaluate_post_maintenance(evidence)
    assert result["pass"] is True
    assert "POST_MAINTENANCE_ALARM_REVIEW_REQUIRED" in result["warnings"]


def test_pending_sns_is_a_manual_warning(evidence):
    evidence["sns"]["status"] = "PendingConfirmation"
    result = evaluate_post_maintenance(evidence)
    assert result["pass"] is True
    assert "MANUAL_SNS_CONFIRMATION_REQUIRED" in result["warnings"]


@pytest.mark.parametrize(
    ("mutate", "failure"),
    [
        (
            lambda item: item["rds"].update(DBInstanceClass="db.t4g.medium"),
            "RDS_DBINSTANCECLASS_INVALID",
        ),
        (
            lambda item: item["rds"]["PendingModifiedValues"].update(
                DBInstanceClass="db.t4g.small"
            ),
            "RDS_CLASS_STILL_PENDING",
        ),
        (lambda item: item["pitr"].update(pass_=False), "PITR_GATE_FAILED"),
        (
            lambda item: item["manual_snapshot"].update(Encrypted=False),
            "MANUAL_SNAPSHOT_UNENCRYPTED",
        ),
        (lambda item: item["ecs_service"].update(runningCount=0), "ECS_COUNTS_INVALID"),
        (
            lambda item: item.update(target_states=["unhealthy"]),
            "ALB_TARGET_NOT_HEALTHY",
        ),
        (lambda item: item["http_status"].update({"/health": 503}), "API_SMOKE_FAILED"),
        (lambda item: item["alarms"].pop(), "PRODUCTION_ALARM_INVENTORY_INVALID"),
        (lambda item: item["staging"].update(rds=1), "STAGING_IDLE_DRIFT"),
    ],
)
def test_required_checks_fail_closed(evidence, mutate, failure):
    candidate = deepcopy(evidence)
    mutate(candidate)
    if failure == "PITR_GATE_FAILED":
        candidate["pitr"]["pass"] = False
    result = evaluate_post_maintenance(candidate)
    assert result["pass"] is False
    assert failure in result["failures"]
