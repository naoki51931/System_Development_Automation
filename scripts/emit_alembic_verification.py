"""Emit a machine-readable Alembic head from the protected read-only task."""

import contextlib
import hashlib
import io
import json

from alembic import command
from alembic.config import Config

from scripts.verify_production_migration_attestation import ALEMBIC_HEAD


def main():
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        command.current(Config("alembic.ini"), check_heads=True)
    raw = output.getvalue()
    observed = ALEMBIC_HEAD if ALEMBIC_HEAD in raw else ""
    result = {
        "observed_alembic_head": observed,
        "output_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }
    print("ALEMBIC_VERIFICATION_RESULT=" + json.dumps(result, separators=(",", ":")))
    if observed != ALEMBIC_HEAD:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
