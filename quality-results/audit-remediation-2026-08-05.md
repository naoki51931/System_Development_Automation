# Audit remediation evidence — 2026-08-05 UTC

## Implemented

- Explicit worker registry for all eight requested job families; unknown types are non-retryable and dead-lettered.
- Claim transaction is committed before handler work. Success completion is a lease-owner compare-and-set. Handler failure never completes a job.
- Lease heartbeat runs in a separate session at a configurable interval (default 20 seconds for a 60-second lease), never increments attempts, and treats DB/owner failure as lease loss.
- Notification/email use local mock providers only. Maintenance uses existing UTC/idempotent billing transitions. Completed documents are verified against storage metadata.
- Atomic worker health status with PID, DB, last poll/heartbeat, error and dead-letter count; Compose health enabled.
- Next standalone runtime uses `.next/standalone`, static/public copies, non-root user, `node server.js`, and `HOSTNAME=0.0.0.0`.
- Explicit production-refusing E2E setup script guarded by `APP_ENABLE_E2E_SEED=true`.
- Runtime-transitive PostCSS upgraded 8.5.18 → 8.5.23 without a major update.
- Migration `6b1e...` now preflights existing status rows and accurately documents DROP/ADD CHECK locking and downgrade destruction.

## Commands and observed results

- `docker compose build backend worker frontend`: PASS.
- `ruff check .`, `ruff format --check .`, `python -m compileall app`: PASS.
- `pytest --cov=app ...`: 115 passed; overall 79.86%; critical 86.02% (1,477/1,717).
- `npm test`: 34 passed; `npm run build`: PASS; `npm run openapi:check`: PASS.
- `npm audit --omit=dev --json`: 0 vulnerabilities after update.
- `bandit -q -r app -f json`: 0 findings. The audit's five Low findings were test assertions/local mock patterns; no global suppression was added. Two new B108 medium reports during remediation were real hard-coded temp-path concerns and were fixed with `tempfile.gettempdir()` plus environment overrides.
- `docker compose down -v --remove-orphans`, `build --no-cache`, `up -d`: PASS. Final `docker compose ps`: all four services healthy.
- `alembic upgrade head`, normal seed twice: exit 0.
- Latest full browser evidence from the input audit remains 69/69; browsers were not rerun after backend worker/standalone packaging changes.

## Unresolved blockers

The schema does not persist enough immutable resume context on partial document and workflow jobs (source ID, resolved template/settings/access snapshot and deterministic version/billing idempotency key). The remediation therefore fails closed for legacy partial jobs. Implementing automatic resume without those fields would risk duplicate artifacts, versions, or AI charges. No additive migration was introduced because the full contract was not completed and a partial schema would misrepresent readiness.

Final result: **NOT_READY**.
