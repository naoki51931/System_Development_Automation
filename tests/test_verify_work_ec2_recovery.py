import hashlib

from scripts.verify_work_ec2_recovery import verify_restored_files


def test_restored_files_pass_without_returning_contents(tmp_path):
    secret = "never-log-this-secret"
    restored = tmp_path / "repo"
    path = restored / "environment" / "terraform.tfvars"
    path.parent.mkdir(parents=True)
    path.write_text(secret)
    manifest = {
        "files": [
            {
                "path": "environment/terraform.tfvars",
                "size": len(secret),
                "sha256": hashlib.sha256(secret.encode()).hexdigest(),
            }
        ]
    }
    result = verify_restored_files(manifest, restored)
    assert result["pass"] is True
    assert result["status"] == "RESTORE_FILE_HASHES_PASS"
    assert secret not in repr(result)


def test_restored_files_fail_closed_for_missing_or_changed(tmp_path):
    restored = tmp_path / "repo"
    restored.mkdir()
    manifest = {
        "files": [
            {"path": "missing", "size": 1, "sha256": "0" * 64},
            {"path": "/absolute", "size": 1, "sha256": "0" * 64},
        ]
    }
    result = verify_restored_files(manifest, restored)
    assert result["pass"] is False
    assert result["checks"] == [
        {
            "path": "missing",
            "exists": False,
            "size_match": False,
            "hash_match": False,
        },
        {
            "path": "INVALID_PATH",
            "exists": False,
            "size_match": False,
            "hash_match": False,
        },
    ]
