# SystemNavigator AI Web portal and workers

## UI and roles

The separate `frontend` Next.js process provides the shared header, navigation, breadcrumbs, notification affordance, organization/project context, loading/error states, responsive layout, and 404/500 views. Customer views cover dashboard, projects, estimates, contracts, Mock payment, artifacts/reviews, chat/change requests, and maintenance. Internal views cover project/review queues, AI settings (never API keys), estimate/contract administration, maintenance states, organization users/roles, read-only audit logs, and dead letters.

Authorization is enforced by FastAPI using database membership and project roles: customer approvals/payment, PM and owner/admin management, reviewer decisions, developer artifacts, and organization owner/admin membership operations. `system_admin` is deliberately not grantable through organization role APIs. The final active organization owner cannot remove their own last owner role. Every resource query applies `organization_id` before returning data.

## LocalAuth and security

`LocalAuthProvider` selects only active seeded users and issues a one-hour HS256 session cookie (`HttpOnly`, `SameSite=Lax`, `Secure` outside development). The signed token contains only `sub`; organization and role claims cannot be forged because they are loaded from PostgreSQL. Mutations with cookie auth require the double-submit `sn_csrf` cookie/header. Organization switching verifies an active membership. Logout clears both cookies. `APP_ENV=production` or `APP_LOCAL_AUTH_ENABLED=false` disables login. `CognitoAuthProviderStub` never performs network access.

The API and Next.js add no-store cache policy, CSP, frame denial, MIME sniffing denial, same-origin referrer policy, internal action URL validation, safe React text rendering, generic public errors, request timeout, and explicit handling for 401/403/409/422/503. Downloads retain existing tenant checks. No dangerous HTML renderer, token display, card input, API-key input, or actual AWS deletion action exists.

## Worker claim, lease, retry and dead letter

`app.workers.outbox.claim` starts a transaction and executes an ordered `SELECT ... FOR UPDATE SKIP LOCKED`. It claims `queued`/legacy `pending`/ready retry jobs or an expired processing lease, then records `locked_at`, `locked_by`, `lease_expires_at`, `heartbeat_at`, and increments `attempt_count`. Completion records `completed` and `processed_at`. Failure records a sanitized error code and bounded exponential backoff in UTC. When `max_attempts` is reached, the job becomes `dead_letter` with `dead_lettered_at`; only organization administrators can requeue it. Existing unique Outbox keys prevent the same side effect being enqueued twice, and completed jobs are never claimed.

The runner uses local mock notification/email handlers and local document/storage and AI stubs. No production provider can be called. UTC scheduler entry points cover Outbox polling, notification digest/retry/expiry, email and document retry, workflow resume, daily maintenance state calculation, and estimate expiry. `maintenance.run_daily(now=...)` makes date boundaries deterministic.

## Cursor pagination

Projects, notifications, chat messages, audit logs, estimates, artifacts, reviews, email messages, document jobs, workflow jobs, and Outbox events accept `cursor` and `page_size` (maximum 100). Ordering is stable by `created_at DESC, id DESC`. Cursors are HMAC-authenticated and malformed or modified values return `INVALID_CURSOR`; tenant predicates are applied independently of cursor content. Responses are `{items, next_cursor}` with no offset fallback.

## Local integration and migration

`compose.yaml` defines `postgres`, `backend`, `frontend`, and `worker`, with named local volumes. Backend startup applies migrations and idempotent local seed data. Migration `6b1e4c9f2a10` adds only Outbox claim/lease/retry/dead-letter columns and a claim index. `migrations/sql/6b1e4c9f2a10_web_workers.sql` is the offline SQL; it was not applied to RDS.

This phase did not connect to or modify Cognito, Stripe, SES, S3, external AI APIs, RDS, Terraform, AWS, ECR, ECS, or any public environment.
# Quality-gate verification addendum

Post-login navigation performs a same-origin reload so the cookie-auth organization provider is re-established reliably. Organization switching remains server-authorized and clears tenant-scoped session cache. The three-browser suite covers six roles, tenant denial, 403/404/409, Mock payment, chat, review, change requests, notifications, and axe checks on 12 portal/admin routes.

Document rendering injects `DOCUMENT_RENDER_FAILURE` before any artifact, version, hash or local-storage side effect. Worker tests require claim exclusivity, leases/heartbeats, bounded retry, dead letter and idempotency. PostgreSQL deadlock/lock-timeout classification is test-only and exposes no production fault endpoint.
