"""Read-only Terraform CLI boundary for local saved-plan verification.

This module intentionally exposes only ``version`` and ``show -json``.  It
does not contain an apply, destroy, or generic command execution method.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_CREDENTIAL_KEY = re.compile(
    r"(?i)(aws_access_key_id|aws_secret_access_key|aws_session_token|aws_profile|"
    r"aws_default_profile|aws_web_identity_token_file|tf_token_[^=\s]*|"
    r"tf_cli_config_file|google_application_credentials|azure_[^=\s]*|arm_[^=\s]*)"
    r"\s*=\s*[^\s]+"
)
_CREDENTIAL_ENV_PREFIXES = ("AWS_", "GOOGLE_", "AZURE_", "ARM_", "TF_TOKEN_")
_CREDENTIAL_ENV_KEYS = {
    "TF_CLI_CONFIG_FILE",
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
}


@dataclass(frozen=True)
class TerraformCliResult:
    command: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    status: str
    reason: str | None = None


@dataclass(frozen=True)
class SavedPlanVerification:
    result: TerraformCliResult
    verification_status: str
    reason: str | None
    saved_plan_file_sha256_before: str | None
    saved_plan_file_sha256_after: str | None
    terraform_version: str | None
    format_version: str | None
    resource_changes: tuple[dict[str, Any], ...]

    @property
    def plan_document(self) -> dict[str, Any] | None:
        if self.verification_status != "succeeded":
            return None
        return {"resource_changes": list(self.resource_changes)}


def redact_text(value: str) -> str:
    return _CREDENTIAL_KEY.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)


class SafeTerraformCliRunner:
    """Run the fixed, local-only Terraform read commands."""

    def __init__(
        self,
        workspace_root: Path,
        *,
        timeout_seconds: float = 30.0,
        output_limit_bytes: int = 1_000_000,
    ) -> None:
        root = workspace_root.resolve()
        if not root.is_dir():
            raise ValueError("workspace root must be an existing directory")
        self.workspace_root = root
        self.timeout_seconds = timeout_seconds
        self.output_limit_bytes = output_limit_bytes
        binary = shutil.which("terraform")
        if binary is None:
            raise RuntimeError("terraform binary is not available")
        resolved = Path(binary).resolve()
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise RuntimeError("terraform binary is not a regular executable")
        self._binary = resolved

    def _environment(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in ("PATH", "LANG", "LC_ALL"):
            value = os.environ.get(key)
            if value:
                env[key] = value
        env["PATH"] = str(self._binary.parent)
        env["HOME"] = str(self.workspace_root)
        env["TF_IN_AUTOMATION"] = "1"
        return {
            key: value
            for key, value in env.items()
            if key not in _CREDENTIAL_ENV_KEYS
            and not key.startswith(_CREDENTIAL_ENV_PREFIXES)
        }

    def _run(self, argv: list[str]) -> TerraformCliResult:
        allowed = (
            argv == [str(self._binary), "version"]
            or len(argv) == 4
            and argv[0] == str(self._binary)
            and argv[1:3] == ["show", "-json"]
        )
        if not allowed:
            return TerraformCliResult(
                tuple(argv), None, "", "", 0, "blocked", "COMMAND_NOT_ALLOWED"
            )
        started = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                cwd=self.workspace_root,
                env=self._environment(),
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            stdout = redact_text(completed.stdout)
            stderr = redact_text(completed.stderr)
            duration_ms = int((time.monotonic() - started) * 1000)
            if (
                len(stdout.encode()) > self.output_limit_bytes
                or len(stderr.encode()) > self.output_limit_bytes
            ):
                return TerraformCliResult(
                    tuple(argv),
                    completed.returncode,
                    stdout[: self.output_limit_bytes],
                    stderr[: self.output_limit_bytes],
                    duration_ms,
                    "blocked",
                    "OUTPUT_LIMIT_EXCEEDED",
                )
            return TerraformCliResult(
                tuple(argv),
                completed.returncode,
                stdout,
                stderr,
                duration_ms,
                "succeeded" if completed.returncode == 0 else "failed",
                None if completed.returncode == 0 else "TERRAFORM_NONZERO_EXIT",
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            stdout = redact_text(_as_text(exc.stdout))[: self.output_limit_bytes]
            stderr = redact_text(_as_text(exc.stderr))[: self.output_limit_bytes]
            return TerraformCliResult(
                tuple(argv), None, stdout, stderr, duration_ms, "blocked", "TIMEOUT"
            )

    def get_version(self) -> TerraformCliResult:
        return self._run([str(self._binary), "version"])

    def _safe_plan_path(self, saved_plan: Path) -> tuple[Path, os.stat_result] | None:
        candidate = Path(saved_plan)
        if candidate.is_symlink() or not candidate.is_file():
            return None
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError:
            return None
        stat = resolved.stat()
        if not os.path.isfile(resolved) or not stat:
            return None
        return resolved, stat

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def show_saved_plan_json(self, saved_plan: Path) -> SavedPlanVerification:
        safe = self._safe_plan_path(saved_plan)
        if safe is None:
            result = TerraformCliResult(
                (str(self._binary), "show", "-json"),
                None,
                "",
                "",
                0,
                "blocked",
                "UNTRUSTED_SAVED_PLAN_PATH",
            )
            return SavedPlanVerification(
                result, "blocked", result.reason, None, None, None, None, ()
            )
        path, before_stat = safe
        before_hash = self._sha256(path)
        result = self._run([str(self._binary), "show", "-json", str(path)])
        after_stat = path.stat() if path.exists() else None
        after_hash = self._sha256(path) if after_stat and path.is_file() else None
        if (
            after_stat is None
            or (before_stat.st_dev, before_stat.st_ino, before_stat.st_size)
            != (after_stat.st_dev, after_stat.st_ino, after_stat.st_size)
            or before_hash != after_hash
        ):
            blocked = TerraformCliResult(
                result.command,
                result.exit_code,
                result.stdout,
                result.stderr,
                result.duration_ms,
                "blocked",
                "SAVED_PLAN_FILE_CHANGED",
            )
            return SavedPlanVerification(
                blocked,
                "blocked",
                blocked.reason,
                before_hash,
                after_hash,
                None,
                None,
                (),
            )
        if result.status != "succeeded":
            return SavedPlanVerification(
                result, "failed", result.reason, before_hash, after_hash, None, None, ()
            )
        try:
            document = json.loads(result.stdout)
            if not isinstance(document, dict):
                raise ValueError("show output must be an object")
            changes = tuple(
                _extract_resource_change(item)
                for item in document.get("resource_changes", [])
                if isinstance(item, dict)
            )
        except (ValueError, TypeError, json.JSONDecodeError):
            failed = TerraformCliResult(
                result.command,
                result.exit_code,
                result.stdout,
                result.stderr,
                result.duration_ms,
                "failed",
                "INVALID_SHOW_JSON",
            )
            return SavedPlanVerification(
                failed, "failed", failed.reason, before_hash, after_hash, None, None, ()
            )
        return SavedPlanVerification(
            result,
            "succeeded",
            None,
            before_hash,
            after_hash,
            str(document.get("terraform_version"))
            if document.get("terraform_version")
            else None,
            str(document.get("format_version"))
            if document.get("format_version")
            else None,
            changes,
        )


def _extract_resource_change(item: dict[str, Any]) -> dict[str, Any]:
    change = item.get("change") if isinstance(item.get("change"), dict) else {}
    actions = (
        change.get("actions", []) if isinstance(change.get("actions"), list) else []
    )
    return {
        "address": item.get("address"),
        "mode": item.get("mode"),
        "type": item.get("type"),
        "name": item.get("name"),
        "actions": [str(action) for action in actions],
    }


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value
