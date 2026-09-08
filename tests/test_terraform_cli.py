import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.terraform_cli import SafeTerraformCliRunner, redact_text
from app.services.deployment import GATE_BLOCKED, check_security_gate


def _make_saved_plan(tmp_path: Path) -> Path:
    (tmp_path / "main.tf").write_text("", encoding="utf-8")
    subprocess.run(
        ["terraform", "init", "-backend=false", "-input=false"],
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"], "HOME": str(tmp_path)},
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["terraform", "plan", "-input=false", "-out=fixture.tfplan"],
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"], "HOME": str(tmp_path)},
        check=True,
        capture_output=True,
        text=True,
    )
    return tmp_path / "fixture.tfplan"


def test_version_and_saved_plan_show_are_read_only(tmp_path: Path):
    plan = _make_saved_plan(tmp_path)
    runner = SafeTerraformCliRunner(tmp_path)
    version = runner.get_version()
    verification = runner.show_saved_plan_json(plan)
    assert version.status == "succeeded"
    assert verification.verification_status == "succeeded"
    assert (
        verification.saved_plan_file_sha256_before
        == verification.saved_plan_file_sha256_after
    )
    assert verification.resource_changes == ()
    assert not hasattr(runner, "apply")
    assert not hasattr(runner, "execute")


def test_environment_is_scrubbed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    runner = SafeTerraformCliRunner(tmp_path)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-inherit")
    monkeypatch.setenv("TF_TOKEN_registry", "must-not-inherit")
    env = runner._environment()
    assert all(
        not key.startswith(("AWS_", "GOOGLE_", "AZURE_", "ARM_", "TF_TOKEN_"))
        for key in env
    )
    assert "TF_CLI_CONFIG_FILE" not in env


def test_process_uses_fixed_argv_cwd_and_shell_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    runner = SafeTerraformCliRunner(tmp_path)
    observed = {}
    completed = type("Completed", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    def capture(*args, **kwargs):
        observed.update(kwargs)
        observed["argv"] = args[0]
        return completed

    monkeypatch.setattr("app.services.terraform_cli.subprocess.run", capture)
    assert runner.get_version().status == "succeeded"
    assert observed["argv"] == [str(runner._binary), "version"]
    assert observed["shell"] is False
    assert observed["cwd"] == tmp_path.resolve()


def test_arbitrary_command_is_rejected(tmp_path: Path):
    runner = SafeTerraformCliRunner(tmp_path)
    result = runner._run([str(runner._binary), "apply", "fixture.tfplan"])
    assert result.status == "blocked"
    assert result.reason == "COMMAND_NOT_ALLOWED"


@pytest.mark.parametrize(
    "path", [Path("../outside.tfplan"), Path("/tmp/outside.tfplan")]
)
def test_untrusted_plan_path_is_blocked(tmp_path: Path, path: Path):
    runner = SafeTerraformCliRunner(tmp_path)
    result = runner.show_saved_plan_json(path)
    assert result.verification_status == "blocked"
    assert result.reason == "UNTRUSTED_SAVED_PLAN_PATH"


def test_symlink_and_non_regular_plan_are_blocked(tmp_path: Path):
    target = tmp_path / "target.tfplan"
    target.write_bytes(b"not-a-plan")
    link = tmp_path / "link.tfplan"
    link.symlink_to(target)
    runner = SafeTerraformCliRunner(tmp_path)
    assert runner.show_saved_plan_json(link).reason == "UNTRUSTED_SAVED_PLAN_PATH"
    directory = tmp_path / "directory.tfplan"
    directory.mkdir()
    assert runner.show_saved_plan_json(directory).reason == "UNTRUSTED_SAVED_PLAN_PATH"


def test_mutation_after_cli_is_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan = tmp_path / "fixture.tfplan"
    plan.write_bytes(b"fixture")
    runner = SafeTerraformCliRunner(tmp_path)
    original = runner._run

    def mutate(argv: list[str]):
        result = original([str(runner._binary), "version"])
        plan.write_bytes(b"mutated")
        return result

    monkeypatch.setattr(runner, "_run", mutate)
    result = runner.show_saved_plan_json(plan)
    assert result.verification_status == "blocked"
    assert result.reason == "SAVED_PLAN_FILE_CHANGED"


def test_timeout_nonzero_output_limit_and_redaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    runner = SafeTerraformCliRunner(tmp_path, timeout_seconds=30, output_limit_bytes=4)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1, output=b"secret")

    monkeypatch.setattr("app.services.terraform_cli.subprocess.run", timeout)
    assert runner._run([str(runner._binary), "version"]).reason == "TIMEOUT"
    assert "AWS_SECRET_ACCESS_KEY=[REDACTED]" in redact_text(
        "AWS_SECRET_ACCESS_KEY=secret"
    )


def test_output_limit_is_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    runner = SafeTerraformCliRunner(tmp_path, output_limit_bytes=4)
    completed = type(
        "Completed",
        (),
        {
            "returncode": 0,
            "stdout": "12345",
            "stderr": "",
        },
    )()
    monkeypatch.setattr(
        "app.services.terraform_cli.subprocess.run", lambda *a, **k: completed
    )
    assert (
        runner._run([str(runner._binary), "version"]).reason == "OUTPUT_LIMIT_EXCEEDED"
    )


def test_resource_extraction_is_minimal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    plan = tmp_path / "fixture.tfplan"
    plan.write_bytes(b"fixture")
    runner = SafeTerraformCliRunner(tmp_path)
    result_type = type(
        "Result",
        (),
        {
            "command": ("terraform", "show", "-json", str(plan)),
            "exit_code": 0,
            "stdout": '{"format_version":"1.0","terraform_version":"1.15.8","resource_changes":[{"address":"x","mode":"managed","type":"local","name":"x","change":{"actions":["create","delete"]}}]}',
            "stderr": "",
            "duration_ms": 1,
            "status": "succeeded",
            "reason": None,
        },
    )
    monkeypatch.setattr(runner, "_run", lambda argv: result_type())
    verification = runner.show_saved_plan_json(plan)
    assert verification.resource_changes == (
        {
            "address": "x",
            "mode": "managed",
            "type": "local",
            "name": "x",
            "actions": ["create", "delete"],
        },
    )


def test_resource_changes_feed_existing_security_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    plan = tmp_path / "fixture.tfplan"
    plan.write_bytes(b"fixture")
    runner = SafeTerraformCliRunner(tmp_path)
    result_type = type(
        "Result",
        (),
        {
            "command": (str(runner._binary), "show", "-json", str(plan)),
            "exit_code": 0,
            "stdout": '{"resource_changes":[{"address":"local.x","mode":"managed","type":"local","name":"x","change":{"actions":["delete"]}}]}',
            "stderr": "",
            "duration_ms": 1,
            "status": "succeeded",
            "reason": None,
        },
    )
    monkeypatch.setattr(runner, "_run", lambda argv: result_type())
    verification = runner.show_saved_plan_json(plan)
    gate = check_security_gate(
        SimpleNamespace(
            environment="staging",
            target_environment="staging",
            aws_account_id="123",
            aws_region="local",
            terraform_state_identity="state/staging",
            terraform_root="fixture",
        ),
        verification.plan_document or {},
        expected_account_id="123",
        expected_region="local",
        expected_root="fixture",
        expected_state_identity="state/staging",
    )
    assert verification.verification_status == "succeeded"
    assert gate.status == GATE_BLOCKED
    assert "UNEXPECTED_DESTROY" in gate.reasons


def test_invalid_show_json_and_nonzero_are_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    plan = tmp_path / "fixture.tfplan"
    plan.write_bytes(b"fixture")
    runner = SafeTerraformCliRunner(tmp_path)
    monkeypatch.setattr(
        runner,
        "_run",
        lambda argv: runner._run.__wrapped__(argv)
        if False
        else type(
            "R",
            (),
            {
                "command": tuple(argv),
                "exit_code": 1,
                "stdout": "",
                "stderr": "bad",
                "duration_ms": 1,
                "status": "failed",
                "reason": "TERRAFORM_NONZERO_EXIT",
            },
        )(),
    )
    result = runner.show_saved_plan_json(plan)
    assert result.verification_status == "failed"
    assert result.reason == "TERRAFORM_NONZERO_EXIT"


def test_invalid_show_json_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    plan = tmp_path / "fixture.tfplan"
    plan.write_bytes(b"fixture")
    runner = SafeTerraformCliRunner(tmp_path)
    result_type = type(
        "Result",
        (),
        {
            "command": (str(runner._binary), "show", "-json", str(plan)),
            "exit_code": 0,
            "stdout": "not-json",
            "stderr": "",
            "duration_ms": 1,
            "status": "succeeded",
            "reason": None,
        },
    )
    monkeypatch.setattr(runner, "_run", lambda argv: result_type())
    result = runner.show_saved_plan_json(plan)
    assert result.verification_status == "failed"
    assert result.reason == "INVALID_SHOW_JSON"
