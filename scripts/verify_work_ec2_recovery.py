#!/usr/bin/env python3
"""Verify restored work-EC2 files against a non-secret recovery manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_restored_files(
    manifest: dict[str, Any], restored_repository: Path
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for item in manifest.get("files") or []:
        relative = item.get("path")
        valid_path = isinstance(relative, str) and not Path(relative).is_absolute()
        path = restored_repository / relative if valid_path else restored_repository
        exists = valid_path and path.is_file()
        size_match = exists and path.stat().st_size == item.get("size")
        hash_match = exists and sha256_file(path) == item.get("sha256")
        checks.append(
            {
                "path": relative if valid_path else "INVALID_PATH",
                "exists": exists,
                "size_match": size_match,
                "hash_match": hash_match,
            }
        )
    passed = bool(checks) and all(
        item["exists"] and item["size_match"] and item["hash_match"] for item in checks
    )
    return {
        "pass": passed,
        "status": "RESTORE_FILE_HASHES_PASS" if passed else "RESTORE_FILE_HASHES_FAIL",
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--restored-repository", required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text())
    result = verify_restored_files(manifest, Path(args.restored_repository))
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
