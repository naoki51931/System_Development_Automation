# Production PITR gate remediation — 2026-08-12 UTC

The gate ran with AWS account `557604519341`, region `eu-west-2`, and assumed role `instanceRoleTerraform`. It uses only RDS `describe-*` APIs; no modify, restore, snapshot creation/deletion, Secrets access, database connection, Terraform apply, or GitHub push was performed.

`scripts/production_pitr_gate.py` is fail-closed for inactive automated backup, immutable resource-ID mismatch, zero or mismatched retention, missing or unordered automated restore window, missing/unavailable/unencrypted latest automated snapshot, recent backup failure, and unavailable/unencrypted manual snapshot. `DBInstance.EarliestRestorableTime` remains an observed field: null emits `PITR_API_FIELD_WARNING` but does not fail by itself.

Unit and static gates passed: 16 PITR tests, Ruff check, Ruff format check, and compileall. Production read-only evaluation returned `PASS` with no failures and the single expected warning.

| Evidence | Result |
|---|---|
| DB instance | `available`; retention 14; `DbiResourceId=db-HLY4EEXCG4CVJNEV2G44AK2IUY` |
| DBInstance Earliest | null; `PITR_API_FIELD_WARNING` only |
| Automated backup | `active`; retention 14; matching `DbiResourceId` |
| RestoreWindow | `2026-08-01T13:20:41.375000+00:00` to `2026-08-12T10:37:31+00:00`; ordered and complete |
| Latest automated snapshot | `rds:ai-platform-prod-postgres-2026-08-11-23-10`; `available`; encrypted |
| Recent backup failures | 0 in the seven-day event window |
| Manual snapshot | `ai-platform-prod-pre-100rpm-downsize-20260812-010957`; `available`; 100%; encrypted |

PITR decision: **PASS**. A temporary restore drill remains optional high-assurance work requiring separate approval.
