# Quality gate summary — 2026-08-06 UTC resume remediation

Local-only verification at baseline `f8e23758f142d89c6bd12cc28ec84e6c2c3d7946` plus the preserved uncommitted work. No GitHub push, cloud, RDS, or external provider was accessed.

| Gate | Result | Evidence |
|---|---|---|
| Backend Test | PASS | 125 passed, 0 failed |
| Backend Overall Coverage | PASS | 83.09%; minimum 80% |
| Critical Service Coverage | PASS | 90.86% (1560/1717); minimum 90% |
| Frontend Test / Coverage | PASS | 34/34; statements/lines 85.18%, branches 74.13%, functions 81.81% |
| Ruff | PASS | check, format check, compileall |
| Security / Secret Scan | PASS | Bandit 0; pip-audit 0; secret scan 0 |
| Migration | PASS | `8d4f2a7c9b11`; downgrade, upgrade, offline SQL, metadata drift zero |
| OpenAPI | PASS | generated client check, no drift |
| Compose | PASS | no-cache build; postgres/backend/frontend/worker healthy |
| Worker Dispatch / Heartbeat / Health | PASS | registry, owner/lease CAS, healthy worker |
| Document Resume | PASS | deterministic version/key, storage hash, missing-snapshot fail-closed |
| AI Workflow Resume | PASS | deterministic run/version/review/cost, source/comment hashes |
| Resume Concurrency | PASS | claim/step idempotency, lease ownership, dead-letter guards |
| Snapshot Immutability | PASS | DB triggers reject snapshot/completed-step mutation |
| Billing Idempotency | PASS | targeted estimate/AI cost/artifact value suite: 36 passed |
| Chromium / Firefox / WebKit | PASS | 23/23 each |
| Accessibility | PASS | 12 routes/browser; axe critical 0, serious 0 |
| npm Audit | PASS | 0 vulnerabilities |
| Performance | PASS | retained 50-user/60-second: 0% errors, detail p95 490 ms, list p95 540 ms |
| Documentation | PASS | seven requested documents synchronized |

The Compose-profile E2E attempt first failed because its quality image lacked browser binaries and its API default was container-local `localhost`. It was rerun against the same healthy Compose stack using the existing host Playwright 1.62.1 cache; all 69 tests passed.

## Final decision: **READY**

Every mandatory local software gate is PASS. Staging remains subject to approval, image pinning, RDS snapshot, SQL-lock review, Terraform, and provider prerequisites.
