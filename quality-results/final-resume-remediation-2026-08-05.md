# Final Resume remediation evidence — completed 2026-08-06 UTC

Work resumed from the existing uncommitted diff at HEAD `f8e23758f142d89c6bd12cc28ec84e6c2c3d7946`. No reset, restore, clean, migration recreation, or uncommitted-file deletion was used. Starting evidence is preserved in `/tmp/systemnavigator-resume-work.patch` and `/tmp/systemnavigator-resume-status.txt`.

## Design and database evidence

Migration `8d4f2a7c9b11` creates immutable `workflow_job_inputs` and durable `workflow_job_steps`. Inputs contain tenant/project, one document/workflow FK, type, schema version `1`, source/actor, access hash, frozen settings/template JSON, payload/hash, deterministic key, and timestamp. Unique job/idempotency constraints, tenant index, restrictive FKs, snapshot immutability, and completed-step immutability are enforced in PostgreSQL.

Document steps: snapshot, version reservation, rendering, rendered hash, storage, verification, DB commit, completion. AI steps: snapshot, run reservation, revision, version reservation, storage, review, cost, state, completion. Deterministic identities prevent duplicate artifact versions, AI runs, reviews, estimate items, pricing snapshots, and AI charges. Source/comment and storage/result SHA-256 mismatches fail closed.

Partial jobs without snapshots are never reconstructed from mutable current data. They set `RESUME_SNAPSHOT_MISSING`, `resume_block_reason=immutable_snapshot_missing`, and `resume_blocked_at` for administrator review/requeue. Completed/dead-letter jobs do not auto-resume; owner/lease CAS rejects a lease-lost worker.

## Executed verification

- Target idempotency: 36 passed, 88 deselected.
- Backend: 125 passed; overall 83.09%; critical 90.86% (1560/1717).
- Critical files: auth dependencies 95.31, verifier 88.89, workflow 90.32, automation 93.87, billing 91.69, communications 86.23, outbox 94.74, pagination 97.92, local auth 77.59, audit 93.75, storage 97.56, payment provider 98.95, AI provider 96.30 percent.
- Migration: current/head `8d4f2a7c9b11`; downgrade/upgrade PASS; offline SQL generated; metadata drift zero.
- Compose: clean no-cache build PASS; four services healthy; repeated seed PASS.
- Frontend: 34 passed; build/OpenAPI PASS; coverage 85.18/74.13/81.81/85.18; npm audit 0.
- Browsers: Chromium/Firefox/WebKit 23 passed each; axe critical 0, serious 0 on 12 routes each.
- Security: Ruff/format/compileall PASS; Bandit, pip-audit, and secret scan 0.
- Performance: retained formal 50-user/60-second evidence, 0% errors, detail p95 490 ms, list p95 540 ms.

Recovery tests replay persisted boundaries and verify the final invariant: one version/key/run/review/cost, immutable source, no partial publication, and fail-closed hashes/snapshots. The Compose E2E infrastructure failure and successful host-cache rerun are both retained in the summary.

## Decision

Local quality gate: **READY**. Staging is eligible only after commit/image pinning and external approval prerequisites. No push or cloud action was performed.
