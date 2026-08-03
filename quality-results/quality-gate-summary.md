# Quality gate summary — 2026-08-03 UTC

Local-only measurements; no AWS, RDS, Cognito, Stripe, SES, S3, external AI, Terraform execution, deployment, or GitHub push occurred.

| Gate | Result | Evidence |
|---|---|---|
| backend tests | PASS | 108 passed |
| lint | FAIL | Ruff reports 274 pre-existing/current style and unused-name findings; includes an undefined pagination symbol in billing API |
| backend coverage | PASS | 82.76% (minimum 80%) |
| important-service coverage | FAIL | aggregate 85.72% (minimum 90%) |
| frontend tests | PASS | 34 passed |
| frontend major-feature coverage | PASS | statements/lines 100%, branches 74.13%, functions 81.81% |
| migration | PASS | additive revision `7c2f9a1e4d30`; offline SQL reviewed |
| OpenAPI | PASS | generated TypeScript drift check and typecheck passed |
| worker concurrency | PASS | three-process exclusive claim/no duplicate test |
| failure injection | PASS | document render rollback/retry/dead letter and PostgreSQL lock timeout tests |
| integration scenario | PASS | complete local API/Mock scenario test |
| performance | FAIL | 50 users/60 s, 0 errors; cold aggregate p95 600 ms and warm 890 ms; normal 500 ms gate missed |
| security | PASS | Bandit and security regression suite passed; pip audit 0 known vulnerabilities |
| secret scan | PASS | current tree and high-confidence history findings 0; values never printed |
| accessibility | PASS | 12 routes, critical 0 and serious 0 in all three browsers |
| Chromium | PASS | 23/23 |
| Firefox | PASS | 23/23 |
| WebKit | PASS | 23/23 |
| Compose clean build | PASS | down `-v`, no-cache build, migration, seed twice, health checks and production build completed |
| Docker build | PASS | multi-stage non-root slim/alpine images |
| documentation | PASS | commands, evidence, limits and staging controls synchronized |
| staging readiness | FAIL | important-service coverage and performance remain below fixed gates |

## Final decision

**NOT_READY**

The gate is not relaxed automatically. Staging remains blocked until lint is clean, important-service aggregate coverage reaches 90%, and the normal API p95 is at most 500 ms under the specified 50-user/60-second local workload.
