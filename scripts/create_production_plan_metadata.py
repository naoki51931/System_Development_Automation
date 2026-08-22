"""Bind a reviewed full Terraform saved plan to verified release evidence."""

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from scripts.verify_production_migration_attestation import SHA40, SHA256, load_json

IMAGE_DIGEST = re.compile(r".+@sha256:([0-9a-f]{64})\Z")


class PlanMetadataError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise PlanMetadataError(message)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _image(plan, name):
    try:
        value = plan["variables"][name]["value"]
    except (KeyError, TypeError) as exc:
        raise PlanMetadataError(f"saved plan lacks {name}") from exc
    require(isinstance(value, str), f"invalid {name}")
    match = IMAGE_DIGEST.fullmatch(value)
    require(match is not None, f"{name} must be digest pinned")
    return value, match.group(1)


def build_metadata(*, release_sha, handoff, plan_path, plan_json):
    require(SHA40.fullmatch(release_sha or ""), "invalid release SHA")
    require(handoff.get("release_sha") == release_sha, "handoff release SHA mismatch")
    for field in (
        "artifact_sha256",
        "alembic_evidence_sha256",
        "verifier_receipt_sha256",
    ):
        require(SHA256.fullmatch(handoff.get(field, "")), f"invalid handoff {field}")
    app_image, app_digest = _image(plan_json, "app_image_uri")
    frontend_image, frontend_digest = _image(plan_json, "frontend_image_uri")
    require(app_image == handoff.get("app_image_uri"), "plan app image mismatch")

    changes = {"add": 0, "change": 0, "replace": 0, "destroy": 0}
    for resource in plan_json.get("resource_changes", []):
        actions = resource.get("change", {}).get("actions", [])
        if actions == ["create"]:
            changes["add"] += 1
        elif actions == ["update"]:
            changes["change"] += 1
        elif actions == ["delete"]:
            changes["destroy"] += 1
        elif "create" in actions and "delete" in actions:
            changes["replace"] += 1
    return {
        "schema_version": 1,
        "release_sha": release_sha,
        "app_image_uri": app_image,
        "app_image_digest": app_digest,
        "frontend_image_uri": frontend_image,
        "frontend_image_digest": frontend_digest,
        "attestation_sha256": handoff["artifact_sha256"],
        "alembic_evidence_sha256": handoff["alembic_evidence_sha256"],
        "verifier_receipt_sha256": handoff["verifier_receipt_sha256"],
        "terraform_plan_sha256": sha256_file(plan_path),
        "resource_changes": changes,
    }


def write_secure_json(path, value):
    path = Path(path)
    require(not path.is_symlink(), "metadata output must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".plan-metadata-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    metadata = build_metadata(
        release_sha=args.release_sha,
        handoff=load_json(args.handoff),
        plan_path=args.plan,
        plan_json=load_json(args.plan_json),
    )
    write_secure_json(args.output, metadata)


if __name__ == "__main__":
    main()
