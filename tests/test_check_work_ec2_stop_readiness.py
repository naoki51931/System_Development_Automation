import hashlib

from scripts.check_work_ec2_stop_readiness import (
    classify_process,
    evaluate_readiness,
    validate_manifest,
)


def valid_evidence():
    return {
        "git_clean": True,
        "manifest_failures": [],
        "active_processes": [],
        "disk_used_percent": 91,
        "identity": {"Account": "557604519341"},
        "region": "eu-west-2",
        "instance": {
            "InstanceId": "i-0add395a2d89805b5",
            "State": "running",
            "RootDeviceType": "ebs",
        },
        "volume": {"VolumeId": "vol-09baf3dfa613ea20d", "State": "in-use"},
        "instance_store_supported": False,
    }


def test_ready_when_every_gate_passes():
    result = evaluate_readiness(valid_evidence())
    assert result == {
        "pass": True,
        "status": "WORK_EC2_READY_FOR_MANUAL_STOP_APPROVAL",
        "failures": [],
    }


def test_blocks_dirty_process_backup_and_disk():
    evidence = valid_evidence()
    evidence.update(
        git_clean=False,
        active_processes=[{"category": "codex", "command": "codex"}],
        disk_used_percent=95,
        manifest_failures=["EXTERNAL_BACKUP_NOT_VERIFIED"],
    )
    result = evaluate_readiness(evidence)
    assert result["pass"] is False
    assert result["status"] == "WORK_EC2_STOP_BLOCKED"
    assert set(result["failures"]) == {
        "EXTERNAL_BACKUP_NOT_VERIFIED",
        "WORKTREE_NOT_CLEAN",
        "ACTIVE_CRITICAL_PROCESS",
        "DISK_CAPACITY_CRITICAL",
    }


def test_blocks_wrong_aws_and_storage_identity():
    evidence = valid_evidence()
    evidence["identity"] = {"Account": "000000000000"}
    evidence["region"] = "us-east-1"
    evidence["instance"] = {
        "InstanceId": "i-wrong",
        "State": "stopped",
        "RootDeviceType": "instance-store",
    }
    evidence["volume"] = {"VolumeId": "vol-wrong", "State": "available"}
    evidence["instance_store_supported"] = True
    result = evaluate_readiness(evidence)
    assert len(result["failures"]) == 7


def test_manifest_hash_validation_never_returns_contents(tmp_path):
    secret = "do-not-print-this-value"
    path = tmp_path / "environment" / "terraform.tfvars"
    path.parent.mkdir()
    path.write_text(secret)
    manifest = {
        "external_backup_verified": True,
        "files": [
            {
                "path": "environment/terraform.tfvars",
                "size": len(secret),
                "sha256": hashlib.sha256(secret.encode()).hexdigest(),
                "secret_bearing": True,
            }
        ],
    }
    failures = validate_manifest(manifest, tmp_path)
    assert failures == []
    assert secret not in repr(failures)


def test_manifest_blocks_missing_or_changed_files(tmp_path):
    manifest = {
        "external_backup_verified": False,
        "files": [
            {
                "path": "environment/backend.hcl",
                "size": 1,
                "sha256": "0" * 64,
                "secret_bearing": True,
            }
        ],
    }
    failures = validate_manifest(manifest, tmp_path)
    assert failures == [
        "CRITICAL_FILE_MISSING:environment/backend.hcl",
        "EXTERNAL_BACKUP_NOT_VERIFIED",
    ]


def test_kernel_migration_thread_is_not_a_user_migration():
    assert classify_process("[migration/0]") is None
    assert classify_process("alembic upgrade head") == "migration"
