import hashlib

import pytest

from scripts.create_production_plan_metadata import PlanMetadataError, build_metadata


def inputs(tmp_path):
    plan = tmp_path / "production.tfplan"
    plan.write_bytes(b"immutable saved plan")
    digest = "a" * 64
    handoff = {
        "release_sha": "b" * 40,
        "app_image_uri": f"registry/app@sha256:{digest}",
        "artifact_sha256": "c" * 64,
        "alembic_evidence_sha256": "d" * 64,
        "verifier_receipt_sha256": "e" * 64,
    }
    plan_json = {
        "variables": {
            "app_image_uri": {"value": handoff["app_image_uri"]},
            "frontend_image_uri": {"value": f"registry/frontend@sha256:{'f' * 64}"},
        },
        "resource_changes": [
            {"change": {"actions": ["create"]}},
            {"change": {"actions": ["update"]}},
            {"change": {"actions": ["delete", "create"]}},
            {"change": {"actions": ["delete"]}},
            {"change": {"actions": ["no-op"]}},
        ],
    }
    return plan, handoff, plan_json


def test_metadata_binds_full_saved_plan_images_and_evidence(tmp_path):
    plan, handoff, plan_json = inputs(tmp_path)
    result = build_metadata(
        release_sha="b" * 40,
        handoff=handoff,
        plan_path=plan,
        plan_json=plan_json,
    )
    assert (
        result["terraform_plan_sha256"] == hashlib.sha256(plan.read_bytes()).hexdigest()
    )
    assert result["resource_changes"] == {
        "add": 1,
        "change": 1,
        "replace": 1,
        "destroy": 1,
    }


def test_metadata_rejects_plan_image_or_release_substitution(tmp_path):
    plan, handoff, plan_json = inputs(tmp_path)
    plan_json["variables"]["app_image_uri"]["value"] = f"registry/app@sha256:{'0' * 64}"
    with pytest.raises(PlanMetadataError, match="app image"):
        build_metadata(
            release_sha="b" * 40,
            handoff=handoff,
            plan_path=plan,
            plan_json=plan_json,
        )
    with pytest.raises(PlanMetadataError, match="release SHA"):
        build_metadata(
            release_sha="1" * 40,
            handoff=handoff,
            plan_path=plan,
            plan_json=plan_json,
        )
