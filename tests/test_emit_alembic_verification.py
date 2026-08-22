import hashlib
import json

import pytest

from scripts import emit_alembic_verification


def result_from(output):
    line = output.strip().removeprefix("ALEMBIC_VERIFICATION_RESULT=")
    return json.loads(line)


def test_emitter_uses_alembic_machine_call_and_hashes_raw_output(monkeypatch, capsys):
    raw = "8d4f2a7c9b11 (head)\n"

    def current(_config, *, check_heads):
        assert check_heads is True
        print(raw, end="")

    monkeypatch.setattr(emit_alembic_verification.command, "current", current)
    emit_alembic_verification.main()
    result = result_from(capsys.readouterr().out)
    assert result == {
        "observed_alembic_head": "8d4f2a7c9b11",
        "output_sha256": hashlib.sha256(raw.encode()).hexdigest(),
    }


def test_emitter_fails_when_database_is_not_at_expected_head(monkeypatch, capsys):
    monkeypatch.setattr(
        emit_alembic_verification.command,
        "current",
        lambda _config, *, check_heads: print("old-revision"),
    )
    with pytest.raises(SystemExit):
        emit_alembic_verification.main()
    assert result_from(capsys.readouterr().out)["observed_alembic_head"] == ""
