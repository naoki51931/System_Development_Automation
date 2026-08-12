#!/usr/bin/env python3
"""Read-only verification for Production after the RDS maintenance window."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import shutil

# This verifier invokes fixed, read-only AWS CLI operations without a shell.
import subprocess  # nosec B404
from typing import Any
import urllib.request

try:
    from scripts.production_pitr_gate import collect_evidence, evaluate_pitr_gate
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from production_pitr_gate import collect_evidence, evaluate_pitr_gate


EXPECTED_ALARMS = {"alb": 4, "ecs": 3, "rds": 6}


def evaluate_post_maintenance(evidence: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    rds = evidence.get("rds") or {}
    pending = rds.get("PendingModifiedValues") or {}
    expected_rds = {
        "DBInstanceClass": "db.t4g.small",
        "DBInstanceStatus": "available",
        "MultiAZ": True,
        "AllocatedStorage": 50,
        "StorageType": "gp2",
        "BackupRetentionPeriod": 14,
        "DeletionProtection": True,
        "StorageEncrypted": True,
        "PubliclyAccessible": False,
    }
    for field, expected in expected_rds.items():
        if rds.get(field) != expected:
            failures.append(f"RDS_{field.upper()}_INVALID")
    if pending.get("DBInstanceClass") is not None:
        failures.append("RDS_CLASS_STILL_PENDING")

    pitr = evidence.get("pitr") or {}
    if pitr.get("pass") is not True:
        failures.append("PITR_GATE_FAILED")
    warnings.extend(pitr.get("warnings") or [])
    snapshot = evidence.get("manual_snapshot") or {}
    if snapshot.get("Status") != "available":
        failures.append("MANUAL_SNAPSHOT_UNAVAILABLE")
    if snapshot.get("Encrypted") is not True:
        failures.append("MANUAL_SNAPSHOT_UNENCRYPTED")

    service = evidence.get("ecs_service") or {}
    task = evidence.get("task_definition") or {}
    if task.get("cpu") != "256" or task.get("memory") != "512":
        failures.append("ECS_CAPACITY_INVALID")
    if (
        service.get("desiredCount"),
        service.get("runningCount"),
        service.get("pendingCount"),
    ) != (1, 1, 0):
        failures.append("ECS_COUNTS_INVALID")
    if service.get("rolloutState") != "COMPLETED":
        failures.append("ECS_DEPLOYMENT_NOT_COMPLETED")
    if evidence.get("target_states") != ["healthy"]:
        failures.append("ALB_TARGET_NOT_HEALTHY")
    if any(code != 200 for code in (evidence.get("http_status") or {}).values()):
        failures.append("API_SMOKE_FAILED")

    alarms = evidence.get("alarms") or []
    categories = Counter(item.get("category") for item in alarms)
    if len(alarms) != 13 or any(
        categories.get(key, 0) != value for key, value in EXPECTED_ALARMS.items()
    ):
        failures.append("PRODUCTION_ALARM_INVENTORY_INVALID")
    alarm_states = Counter(item.get("state") for item in alarms)
    alarm_names = [item.get("name") for item in alarms if item.get("state") == "ALARM"]
    if alarm_names:
        warnings.append("POST_MAINTENANCE_ALARM_REVIEW_REQUIRED")

    sns = evidence.get("sns") or {}
    if (
        sns.get("topic") != "ai-platform-prod-alerts"
        or sns.get("endpoint") != "info@nagi-neco.com"
    ):
        failures.append("PRODUCTION_SNS_INVALID")
    if sns.get("status") == "PendingConfirmation":
        warnings.append("MANUAL_SNS_CONFIRMATION_REQUIRED")
    if evidence.get("alb_state") != "active":
        failures.append("ALB_NOT_ACTIVE")
    if evidence.get("nat_state") != "available":
        failures.append("NAT_NOT_AVAILABLE")
    staging = evidence.get("staging") or {}
    if any(
        staging.get(key) != 0
        for key in ("rds", "alb", "interface_endpoints", "runtime_ecs")
    ):
        failures.append("STAGING_IDLE_DRIFT")

    return {
        "pass": not failures,
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": warnings,
        "alarm_states": dict(alarm_states),
        "alarm_review": alarm_names,
    }


def summarize_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    rds = evidence.get("rds") or {}
    service = evidence.get("ecs_service") or {}
    task = evidence.get("task_definition") or {}
    alarms = evidence.get("alarms") or []
    return {
        "rds": {
            field: rds.get(field)
            for field in (
                "DBInstanceClass",
                "DBInstanceStatus",
                "PendingModifiedValues",
                "MultiAZ",
                "AllocatedStorage",
                "StorageType",
                "BackupRetentionPeriod",
                "DeletionProtection",
                "StorageEncrypted",
                "PubliclyAccessible",
                "PreferredMaintenanceWindow",
            )
        },
        "pitr": evidence.get("pitr"),
        "manual_snapshot": {
            "Status": (evidence.get("manual_snapshot") or {}).get("Status"),
            "Encrypted": (evidence.get("manual_snapshot") or {}).get("Encrypted"),
        },
        "ecs": {
            "taskDefinitionArn": task.get("taskDefinitionArn"),
            "cpu": task.get("cpu"),
            "memory": task.get("memory"),
            "desired": service.get("desiredCount"),
            "running": service.get("runningCount"),
            "pending": service.get("pendingCount"),
            "rollout": service.get("rolloutState"),
            "target_states": evidence.get("target_states"),
        },
        "http_status": evidence.get("http_status"),
        "alarms": {
            "total": len(alarms),
            "categories": dict(Counter(item.get("category") for item in alarms)),
            "states": dict(Counter(item.get("state") for item in alarms)),
            "alarm_names": [
                item.get("name") for item in alarms if item.get("state") == "ALARM"
            ],
        },
        "sns": evidence.get("sns"),
        "alb_state": evidence.get("alb_state"),
        "nat_state": evidence.get("nat_state"),
        "staging": evidence.get("staging"),
    }


def _aws(*args: str) -> Any:
    aws_cli = shutil.which("aws")
    if aws_cli is None:
        raise RuntimeError("AWS CLI is required")
    # The argv list is passed directly and is never evaluated by a shell.
    result = subprocess.run(  # nosec B603
        [aws_cli, *args, "--output", "json"], check=True, capture_output=True, text=True
    )
    return json.loads(result.stdout)


def _get_status(url: str) -> int:
    request = urllib.request.Request(url, method="GET")
    # The operator supplies the expected Production ALB HTTP URL.
    with urllib.request.urlopen(request, timeout=15) as response:  # nosec B310
        return response.status


def collect_post_maintenance(region: str, alb_url: str) -> dict[str, Any]:
    db_id = "ai-platform-prod-postgres"
    snapshot_id = "ai-platform-prod-pre-100rpm-downsize-20260812-010957"
    rds = _aws(
        "rds",
        "describe-db-instances",
        "--db-instance-identifier",
        db_id,
        "--region",
        region,
    )["DBInstances"][0]
    pitr_evidence = collect_evidence(db_id, snapshot_id, region)
    service = _aws(
        "ecs",
        "describe-services",
        "--cluster",
        "ai-platform-prod",
        "--services",
        "ai-platform-prod",
        "--region",
        region,
    )["services"][0]
    task = _aws(
        "ecs",
        "describe-task-definition",
        "--task-definition",
        service["taskDefinition"],
        "--region",
        region,
    )["taskDefinition"]
    service["rolloutState"] = service.get("deployments", [{}])[0].get("rolloutState")
    target_group = _aws(
        "elbv2",
        "describe-target-groups",
        "--names",
        "ai-platform-prod-app",
        "--region",
        region,
    )["TargetGroups"][0]
    target_states = [
        item["TargetHealth"]["State"]
        for item in _aws(
            "elbv2",
            "describe-target-health",
            "--target-group-arn",
            target_group["TargetGroupArn"],
            "--region",
            region,
        )["TargetHealthDescriptions"]
    ]
    raw_alarms = _aws(
        "cloudwatch",
        "describe-alarms",
        "--alarm-name-prefix",
        "ai-platform-prod-",
        "--region",
        region,
    )["MetricAlarms"]
    alarms = []
    for alarm in raw_alarms:
        name = alarm["AlarmName"]
        category = "rds" if "-rds-" in name else "ecs" if "-ecs-" in name else "alb"
        alarms.append(
            {
                "name": name,
                "category": category,
                "state": alarm["StateValue"],
                "reason": alarm.get("StateReason"),
            }
        )
    topic_arn = next(
        item["TopicArn"]
        for item in _aws("sns", "list-topics", "--region", region)["Topics"]
        if item["TopicArn"].endswith(":ai-platform-prod-alerts")
    )
    subscription = next(
        item
        for item in _aws(
            "sns",
            "list-subscriptions-by-topic",
            "--topic-arn",
            topic_arn,
            "--region",
            region,
        )["Subscriptions"]
        if item.get("Endpoint") == "info@nagi-neco.com"
    )
    alb = _aws(
        "elbv2",
        "describe-load-balancers",
        "--names",
        "ai-platform-prod",
        "--region",
        region,
    )["LoadBalancers"][0]
    nat = _aws(
        "ec2",
        "describe-nat-gateways",
        "--nat-gateway-ids",
        "nat-041c10f70dc672ab4",
        "--region",
        region,
    )["NatGateways"][0]
    staging_vpcs = _aws(
        "ec2",
        "describe-vpcs",
        "--filters",
        "Name=tag:Name,Values=system-navigator-staging-vpc",
        "--region",
        region,
    )["Vpcs"]
    endpoint_count = 0
    if staging_vpcs:
        endpoint_count = len(
            _aws(
                "ec2",
                "describe-vpc-endpoints",
                "--filters",
                f"Name=vpc-id,Values={staging_vpcs[0]['VpcId']}",
                "Name=vpc-endpoint-type,Values=Interface",
                "--region",
                region,
            )["VpcEndpoints"]
        )
    return {
        "rds": rds,
        "pitr": evaluate_pitr_gate(pitr_evidence),
        "manual_snapshot": pitr_evidence["manual_snapshot"],
        "ecs_service": service,
        "task_definition": task,
        "target_states": target_states,
        "http_status": {
            path: _get_status(f"{alb_url.rstrip('/')}{path}")
            for path in ("/", "/health", "/docs")
        },
        "alarms": alarms,
        "sns": {
            "topic": "ai-platform-prod-alerts",
            "endpoint": subscription["Endpoint"],
            "status": "PendingConfirmation"
            if subscription["SubscriptionArn"] == "PendingConfirmation"
            else "Confirmed",
        },
        "alb_state": alb["State"]["Code"],
        "nat_state": nat["State"],
        "staging": {
            "rds": len(
                [
                    item
                    for item in _aws(
                        "rds", "describe-db-instances", "--region", region
                    )["DBInstances"]
                    if item["DBInstanceIdentifier"].startswith(
                        "system-navigator-staging"
                    )
                ]
            ),
            "alb": len(
                [
                    item
                    for item in _aws(
                        "elbv2", "describe-load-balancers", "--region", region
                    )["LoadBalancers"]
                    if item["LoadBalancerName"].startswith("system-navigator-staging")
                ]
            ),
            "interface_endpoints": endpoint_count,
            "runtime_ecs": len(
                [
                    arn
                    for arn in _aws("ecs", "list-clusters", "--region", region)[
                        "clusterArns"
                    ]
                    if "system-navigator-staging" in arn
                ]
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="eu-west-2")
    parser.add_argument("--alb-url", required=True)
    args = parser.parse_args()
    evidence = collect_post_maintenance(args.region, args.alb_url)
    result = evaluate_post_maintenance(evidence)
    result["observed"] = summarize_evidence(evidence)
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
