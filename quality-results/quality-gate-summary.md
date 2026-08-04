# Quality gate summary — 2026-08-04 UTC

Local only. No AWS/RDS/Terraform/ECR/ECS/Cognito/Stripe/SES/S3/external AI,
GitHub push, or public environment was accessed or changed.

| Gate | Result | Evidence |
|---|---|---|
| ruff | PASS | `ruff check .`: 0 errors |
| undefined symbols | PASS | F821/F822/F823: 0; billing uses shared cursor paginator |
| backend tests | PASS | 110 passed |
| backend coverage | PASS | 81.43% (minimum 80%) |
| critical service coverage | FAIL | 86.04% (1,461/1,698; minimum 90%) |
| frontend tests | PASS | 34 passed |
| frontend coverage | PASS | unchanged: statements/lines 100%, branches 74.13%, functions 81.81% |
| migration | PASS | local migration regressions; no remote execution |
| OpenAPI | PASS | generated TypeScript drift check passed |
| worker concurrency | PASS | concurrency regressions green |
| failure injection | PASS | rollback/retry/dead-letter regressions green |
| integration scenario | PASS | local Mock-provider scenario passed |
| normal API performance | FAIL | project detail p95 609 ms (>500 ms), 0% errors |
| list API performance | PASS | worst p95 684 ms (<1 s), 0% errors |
| security | PASS | Bandit 0; pip-audit 0 known vulnerabilities |
| secret scan | PASS | 0 findings |
| accessibility | PASS | 12 routes/browser; critical/serious 0 |
| Chromium | PASS | 23/23 |
| Firefox | PASS | 23/23 |
| WebKit | PASS | 23/23 |
| Compose clean build | PASS | images rebuilt; services healthy |
| npm audit | BLOCKED | exit 1, `EAI_AGAIN`; last success 0, lock hash recorded; not PASS |
| documentation | PASS | evidence synchronized |
| staging readiness | FAIL | coverage/performance mandatory gates fail |

Start-commit classification with pinned Ruff produced 290 (the supplied prior count
was 274): undefined reference 1; unused imports/variables 34; import layout 10;
production style 124; test-specific 116; migration-specific 5. Complexity and
exception categories were 0 under the configured rules. No Ruff rule, `noqa`,
per-file ignore, or exclusion was added.

## Final decision: **NOT_READY**

Critical-service coverage and normal API performance are mandatory failures. npm
audit is independently **BLOCKED**, never PASS. Staging remains prohibited.
