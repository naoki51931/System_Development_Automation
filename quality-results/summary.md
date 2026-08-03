# Local staging-readiness results — 2026-08-03 UTC

These are local reference results, not a production SLA.

- Backend: 100 passed; total coverage 75% (target 80% not met). Service coverage includes AI providers 93%, Outbox 93%, billing 85%, communications 82%, storage 86%, automation service 75%, workflow 74%; the important-service 90% target is not met overall.
- Frontend: 3 unit tests passed; statement coverage 21.21% (target 70% not met). Production build and TypeScript check passed before generated dependencies were removed for disk recovery.
- OpenAPI: FastAPI export and `openapi-typescript` drift check passed. Generated file contains a no-manual-edit header.
- Playwright API E2E: 9 passed — six roles, tenant isolation, developer approval rejection, organization-admin access, and integrated estimate/contract/Mock-payment/artifact/chat/change-request flow.
- Integrated flow coverage gap: AI review/revision/re-review, PDF/email and additional estimate remain covered by backend service tests rather than the single browser/API scenario; this blocks staging.
- Three-process worker test passed for 12 jobs with no duplicate claims. Existing tests cover lease reclaim, heartbeat, retry, idempotency, poison/dead-letter and admin retry.
- Fault injection tests passed for production-disable and retry classification; local hooks exist for AI timeout, payment unavailable, email failure, storage failure and worker crash. Document render and simulated deadlock hooks remain unconnected.
- Locust complete scenario: 50 users, 20 seconds, 1,297 requests, 0 failures, aggregate p95 940 ms. List p95 was 670–1,400 ms depending endpoint; chat POST p95 1,300 ms. The normal 500 ms target and some list 1 s targets are not met.
- DB EXPLAIN at `QUALITY_SCALE=0.001`: 0.098–0.224 ms. Outbox uses `LockRows` + index scan. Small-volume project/notification/chat plans include sequential scans; full-scale index confirmation remains required.
- Bandit: 0 findings after fixes. npm audit: 0 vulnerabilities after Vitest upgrade. pip-audit found vulnerable PyJWT 2.10.1; after upgrade to 2.13.0 the final direct-dependency audit found no known vulnerabilities.
- Secret scan: no current-tree or high-confidence Git-history findings. Values were never printed.
- Chromium/Firefox/WebKit UI and axe: not executed locally because browser installation exhausted the 19 GB filesystem. Tests and CI gate are present.
- Compose: backend and worker images built, but clean `compose up --build` failed while installing frontend dependencies due ENOSPC. Partial resources were removed. Full clean rebuild remains blocking.
