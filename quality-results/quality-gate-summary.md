# Quality gate summary — 2026-08-05 UTC remediation

Local-only verification at baseline `4b199b02aebe8a8e41c276279479d6daf3f174e4` plus the uncommitted remediation. No cloud/provider/public environment was accessed.

| Gate | Result | Evidence |
|---|---|---|
| Backend Test | PASS | 115 passed, 1 warning |
| Backend Coverage | FAIL | 79.86%; required 80% |
| Critical Service Coverage | FAIL | 86.02% (1,477/1,717); required 90% |
| Frontend Test | PASS | Vitest 34/34 |
| Frontend Coverage | PASS | Prior audited 85.18/74.13/81.81%; no coverage-affecting UI change |
| Ruff | PASS | `ruff check .` and `ruff format --check .` |
| Security | PASS | Bandit app scan 0 findings; pip-audit previously 0; npm audit 0 |
| Secret Scan | PASS | Prior audit 0 findings; no secret material added |
| Migration | PASS | Local migration/seed succeeded; `6b1e...` now preflights rows and documents CHECK replacement locks/downgrade |
| OpenAPI | PASS | `npm run openapi:check`, no drift |
| Compose | PASS | Clean no-cache rebuild; postgres/backend/frontend/worker all healthy |
| Playwright Chromium | PASS | Latest executed audit: 23/23 |
| Playwright Firefox | PASS | Latest executed audit: 23/23 |
| Playwright WebKit | PASS | Latest executed audit: 23/23 |
| Accessibility | PASS | Latest executed audit: axe critical/serious 0 on 12 routes/browser |
| Worker Dispatch | PASS | Explicit 8-type registry; success, retry, unknown/dead-letter tests |
| Worker Heartbeat | PASS | Owner CAS lease extension; interval injection; stop-on-complete/failure tests |
| Worker Resume | FAIL | Expired Outbox lease works; legacy partial document/AI workflow rows fail closed rather than complete automatically |
| Worker Health | PASS | PID/poll/DB/dead-letter status; Compose worker healthy |
| npm Audit | PASS | PostCSS 8.5.23; GHSA-fxqj-rqcc-2cmp remediated; 0 vulnerabilities; lock SHA-256 `342cbfba...655656` |
| Performance | PASS | Existing formal 50-user/60s: 0% errors; detail p95 490 ms, list p95 540 ms |
| Documentation | PASS | Worker, Compose, E2E, standalone, npm audit, migration and decision synchronized |

## Final decision: **NOT_READY**

Backend overall coverage, critical-service coverage, and Worker Resume are mandatory failures. Staging migration remains prohibited. npm audit is a current PASS and is not treated as blocked.
