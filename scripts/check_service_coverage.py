#!/usr/bin/env python3
"""Enforce the fixed critical-service coverage gate from coverage.py JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


CRITICAL_SERVICES = {
    "authentication.dependencies": "app/auth/dependencies.py",
    "authentication.verifier": "app/auth/verifier.py",
    "workflow": "app/services/workflow.py",
    "automation": "app/services/automation.py",
    "billing": "app/services/billing.py",
    "communications": "app/services/communications.py",
    "outbox": "app/workers/outbox.py",
    "pagination": "app/api/pagination.py",
    "local_auth": "app/api/local_auth.py",
    "audit": "app/audit.py",
    "storage": "app/services/storage.py",
    "payment_provider": "app/services/payment_providers.py",
    "ai_provider": "app/services/ai_providers.py",
}

# Generated migrations, seed commands, package __init__.py files, and quality data
# generators are excluded because they are not request/service behavior. No
# production service module is excluded from the fixed list above.
EXCLUSIONS = {
    "migrations/": "Alembic generated/reviewed separately by the migration gate",
    "**/__init__.py": "package markers contain no service decisions",
    "app/quality/seed_*.py": "local quality-data generators, not runtime services",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "coverage_json", nargs="?", default="quality-results/backend-coverage.json"
    )
    parser.add_argument("--minimum", type=float, default=90.0)
    args = parser.parse_args()

    report = json.loads(Path(args.coverage_json).read_text(encoding="utf-8"))
    files = report["files"]
    total_statements = 0
    covered_statements = 0

    print(f"overall: {report['totals']['percent_covered']:.2f}%")
    for name, filename in CRITICAL_SERVICES.items():
        if filename not in files:
            raise SystemExit(f"coverage report is missing critical service: {filename}")
        summary = files[filename]["summary"]
        statements = int(summary["num_statements"])
        covered = int(summary["covered_lines"])
        percent = 100.0 if statements == 0 else covered * 100.0 / statements
        total_statements += statements
        covered_statements += covered
        print(f"{name}: {percent:.2f}% ({covered}/{statements})")

    aggregate = covered_statements * 100.0 / total_statements
    print(
        f"critical-service aggregate: {aggregate:.2f}% "
        f"({covered_statements}/{total_statements}); minimum: {args.minimum:.2f}%"
    )
    print("exclusions:")
    for pattern, reason in EXCLUSIONS.items():
        print(f"  {pattern}: {reason}")
    return 0 if aggregate >= args.minimum else 1


if __name__ == "__main__":
    raise SystemExit(main())
