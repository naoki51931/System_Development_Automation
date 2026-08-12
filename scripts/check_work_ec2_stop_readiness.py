#!/usr/bin/env python3
"""Fail-closed, read-only readiness check for the work EC2 instance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
# All subprocess calls use fixed read-only commands without a shell.
import subprocess  # nosec B404
from typing import Any


EXPECTED_ACCOUNT = "557604519341"
EXPECTED_REGION = "eu-west-2"
EXPECTED_INSTANCE = "i-0add395a2d89805b5"
EXPECTED_VOLUME = "vol-09baf3dfa613ea20d"
PROCESS_MARKERS = {
    "terraform": ("terraform apply", "terraform plan"),
    "docker_build": ("docker build", "docker compose build"),
    "migration": ("alembic", "migration"),
    "tests": ("pytest", "playwright", "npm run build"),
    "local_database": ("postgres",),
    "codex": ("codex",),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest(manifest: dict[str, Any], root: Path) -> list[str]:
    failures: list[str] = []
    files = manifest.get("files") or []
    if not files:
        return ["RECOVERY_MANIFEST_EMPTY"]
    for item in files:
        relative = item.get("path")
        if not isinstance(relative, str) or Path(relative).is_absolute():
            failures.append("RECOVERY_MANIFEST_PATH_INVALID")
            continue
        path = root / relative
        if not path.is_file():
            failures.append(f"CRITICAL_FILE_MISSING:{relative}")
            continue
        if path.stat().st_size != item.get("size"):
            failures.append(f"CRITICAL_FILE_SIZE_MISMATCH:{relative}")
        if sha256_file(path) != item.get("sha256"):
            failures.append(f"CRITICAL_FILE_HASH_MISMATCH:{relative}")
        if item.get("secret_bearing") is not True:
            failures.append(f"CRITICAL_FILE_CLASSIFICATION_INVALID:{relative}")
    if manifest.get("external_backup_verified") is not True:
        failures.append("EXTERNAL_BACKUP_NOT_VERIFIED")
    return failures


def evaluate_readiness(evidence: dict[str, Any]) -> dict[str, Any]:
    failures = list(evidence.get("manifest_failures") or [])
    if evidence.get("git_clean") is not True:
        failures.append("WORKTREE_NOT_CLEAN")
    if evidence.get("active_processes"):
        failures.append("ACTIVE_CRITICAL_PROCESS")
    if evidence.get("disk_used_percent", 101) >= 95:
        failures.append("DISK_CAPACITY_CRITICAL")
    identity = evidence.get("identity") or {}
    if identity.get("Account") != EXPECTED_ACCOUNT:
        failures.append("AWS_ACCOUNT_MISMATCH")
    if evidence.get("region") != EXPECTED_REGION:
        failures.append("AWS_REGION_MISMATCH")
    instance = evidence.get("instance") or {}
    if instance.get("InstanceId") != EXPECTED_INSTANCE:
        failures.append("INSTANCE_ID_MISMATCH")
    if instance.get("State") != "running":
        failures.append("INSTANCE_NOT_RUNNING")
    if instance.get("RootDeviceType") != "ebs":
        failures.append("ROOT_NOT_EBS")
    volume = evidence.get("volume") or {}
    if volume.get("VolumeId") != EXPECTED_VOLUME or volume.get("State") != "in-use":
        failures.append("EXPECTED_EBS_NOT_ATTACHED")
    if evidence.get("instance_store_supported") is not False:
        failures.append("INSTANCE_STORE_RISK")
    failures = list(dict.fromkeys(failures))
    return {
        "pass": not failures,
        "status": (
            "WORK_EC2_READY_FOR_MANUAL_STOP_APPROVAL"
            if not failures
            else "WORK_EC2_STOP_BLOCKED"
        ),
        "failures": failures,
    }


def _run_json(args: list[str]) -> Any:
    result = subprocess.run(  # nosec B603
        args, check=True, capture_output=True, text=True
    )
    return json.loads(result.stdout)


def collect_evidence(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    aws = shutil.which("aws")
    git = shutil.which("git")
    ps = shutil.which("ps")
    if not aws or not git or not ps:
        raise RuntimeError("aws, git, and ps are required")
    git_status = subprocess.run(  # nosec B603
        [git, "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    process_lines = subprocess.run(  # nosec B603
        [ps, "-eo", "pid=,args="], check=True, capture_output=True, text=True
    ).stdout.splitlines()
    active: list[dict[str, str]] = []
    for line in process_lines:
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        if (
            pid_text == str(os.getpid())
            or "check_work_ec2_stop_readiness.py" in command
        ):
            continue
        lowered = command.lower()
        for category, markers in PROCESS_MARKERS.items():
            if any(marker in lowered for marker in markers):
                active.append({"category": category, "command": command.split()[0]})
                break
    disk = shutil.disk_usage(root)
    identity = _run_json([aws, "sts", "get-caller-identity", "--output", "json"])
    region = subprocess.run(  # nosec B603
        [aws, "configure", "get", "region"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    instance_raw = _run_json(
        [
            aws,
            "ec2",
            "describe-instances",
            "--instance-ids",
            EXPECTED_INSTANCE,
            "--region",
            EXPECTED_REGION,
            "--output",
            "json",
        ]
    )["Reservations"][0]["Instances"][0]
    volume = _run_json(
        [
            aws,
            "ec2",
            "describe-volumes",
            "--volume-ids",
            EXPECTED_VOLUME,
            "--region",
            EXPECTED_REGION,
            "--output",
            "json",
        ]
    )["Volumes"][0]
    instance_type = _run_json(
        [
            aws,
            "ec2",
            "describe-instance-types",
            "--instance-types",
            instance_raw["InstanceType"],
            "--region",
            EXPECTED_REGION,
            "--output",
            "json",
        ]
    )["InstanceTypes"][0]
    return {
        "git_clean": not git_status,
        "manifest_failures": validate_manifest(manifest, root),
        "active_processes": active,
        "disk_used_percent": round((disk.used / disk.total) * 100),
        "identity": {"Account": identity.get("Account")},
        "region": region,
        "instance": {
            "InstanceId": instance_raw.get("InstanceId"),
            "State": (instance_raw.get("State") or {}).get("Name"),
            "RootDeviceType": instance_raw.get("RootDeviceType"),
        },
        "volume": {"VolumeId": volume.get("VolumeId"), "State": volume.get("State")},
        "instance_store_supported": instance_type.get("InstanceStorageSupported"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default="quality-results/work-ec2-recovery-manifest.json",
    )
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    manifest = json.loads((root / args.manifest).read_text())
    evidence = collect_evidence(root, manifest)
    result = evaluate_readiness(evidence)
    result["observed"] = evidence
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
