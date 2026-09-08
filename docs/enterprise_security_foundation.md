# Enterprise Security Foundation

## Purpose

Phase 1 adds the backend security foundation required before connecting an AI
Agent or deployment executor. It does not execute AI, AWS, Terraform, staging,
or production operations.

## Permission Model

`app/auth/permissions.py` is the deny-by-default permission matrix. A decision
uses the authenticated user, organization membership, organization roles,
optional project membership roles, and a resource action. Unknown roles and
actions have no permissions. Cross-tenant resource access is rejected before
role evaluation.

Organization owners/admins retain organization-wide permissions. Project
manager, reviewer, developer, customer, and viewer permissions are scoped to
their ProjectMember record when a project context is supplied. Existing seeded
role names are reused.

## Protected Actions

The following actions are representable but have no executor in this phase:

- `deployment.staging`
- `deployment.production`
- `terraform.plan`
- `terraform.apply`
- `secret.access`
- `permission.change`

`can_execute_protected_action` is an authorization decision point only. It
requires an approved record and an explicit executor permission.

## Approval Lifecycle

`ProtectedApproval` stores requested/approved/rejected/expired/executed state,
tenant and project scope, requester and decider, action, resource, target
version, reason, expiry, and future `plan_checksum`/`artifact_digest` fields.
Existing Artifact `ApprovalEvent` remains the artifact-review history; the new
model is the generic protected-action gate.

## Four Eyes Control

Production deployment, Terraform apply, secret access, and permission change
require a distinct approver. The requester cannot approve those records.

## Stale Approval Protection

An approved record with `target_version` is executable only when the executor
supplies the same current version. Rejected, expired, requested, or executed
records are not executable.

## Audit Event Model

The existing `AuditLog` is extended with `actor_type`, `approval_id`,
`correlation_id`, `result`, and `reason`. Approval request/approve/reject and
permission changes emit events. Security-relevant denials can also be emitted.
Audit records have no application update/delete API and are treated as
application-level append-only. Database administrator tamper resistance,
WORM storage, and export retention are future work.

## Actor Types

`human`, `system`, and `ai_agent` are representable. `ai_agent` has zero
permissions by default and no agent implementation exists in this phase.

## Tenant Boundary

Organization membership is checked first. Project approval requests also verify
that the project belongs to the requested organization. An approval from a
different organization cannot be decided or executed.

## Known Limitations

- Existing non-approval endpoints still contain legacy role constants and need
  gradual migration to this matrix.
- PostgreSQL RLS, WORM audit storage, SSO/MFA/SCIM, prompt governance, and
  deployment execution are not part of Phase 1.
- The current migration is reviewed only; it must be applied through a future
  separately approved database procedure.

## Legacy Mutation Risk Inventory

The complete mutation inventory is retained here so every legacy action has an
explicit disposition. `Current auth` means the existing backend guard; Matrix
checks were added in addition to it. All rows have an authentication and tenant
boundary (`MISSING_AUTH=0`).

| Method / path | Resource | Current auth and boundary | Required role | Security impact | Matrix permission | Risk |
|---|---|---|---|---|---|---|
| POST `/projects` | project | org membership + project-write roles | owner/admin/PM | project creation | `project.update` | HIGH (migrated) |
| POST `/projects/{id}/start-estimate` | project state | project org membership + write roles + version | owner/admin/PM | workflow state | `project.update` | HIGH (migrated) |
| POST `/projects/{id}/artifacts` | artifact | project tenant + artifact-write roles | owner/admin/PM/developer | artifact creation | legacy | MEDIUM |
| POST `/artifacts/{id}/versions` | artifact version | artifact tenant + artifact-write roles | owner/admin/PM/developer | content/version creation | legacy | MEDIUM |
| POST `/artifact-versions/{id}/reviews` | review | artifact tenant + review roles | owner/admin/PM/reviewer | review assignment | legacy | MEDIUM |
| POST `/reviews/{id}/comments` | review comment | review tenant + review roles | owner/admin/PM/reviewer | review evidence | legacy | LOW |
| POST `/artifact-versions/{id}/submit` | artifact state | artifact tenant + artifact-write roles | owner/admin/PM/developer | lifecycle transition | legacy | MEDIUM |
| POST `/artifact-versions/{id}/approve` | artifact state | artifact tenant + approval roles + business rules | owner/admin/PM/customer | release/artifact approval | `artifact.review` | HIGH (migrated) |
| POST `/artifact-versions/{id}/request-changes` | artifact state | artifact tenant + review roles + version | owner/admin/PM/reviewer | lifecycle transition | legacy | MEDIUM |
| POST `/notifications/{id}/read`, POST `/notifications/read-all` | notification | authenticated org tenant | member | user state only | legacy | LOW |
| PATCH `/notification-preferences/{id}` | notification preference | authenticated org tenant + owner/self guard | member/admin | notification behavior | legacy | LOW |
| POST `/projects/{id}/documents/generate` | document job | project tenant + project roles | owner/admin/PM | generated artifact/job | legacy | MEDIUM |
| POST `/artifact-versions/{id}/send-email` | document delivery | artifact tenant + privileged roles | owner/admin/PM/reviewer | external delivery | legacy | MEDIUM |
| POST `/projects/{id}/chat-rooms` | chat room | project tenant + project membership | project member | collaboration data | legacy | LOW |
| POST `/chat-rooms/{id}/messages` | chat message | room tenant + project membership | project member | collaboration data | legacy | LOW |
| PATCH `/chat-messages/{id}`; DELETE same | chat message | tenant + author/privileged guard + version | author/privileged | content mutation | legacy | MEDIUM |
| POST `/chat-messages/{id}/attachments` | attachment | message/artifact tenant | project member | content association | legacy | MEDIUM |
| POST `/chat-messages/{id}/change-requests` | change request | message tenant + project membership | project member | workflow request | legacy | MEDIUM |
| POST `/change-requests/{id}/analyze` | change request | tenant + project access + version | project member | AI analysis state | legacy | MEDIUM |
| POST `/change-requests/{id}/approve`, `/reject` | change request | tenant + role/business guard + version | customer/provider roles | workflow decision | legacy | MEDIUM |
| POST `/projects/{id}/estimates` | estimate | project tenant + billing write roles | owner/admin/PM | financial estimate | `contract.create` | HIGH (migrated) |
| POST `/estimates/{id}/submit`, `/approve`, `/reject` | estimate state | org tenant + billing transition rules | billing roles | financial state | `contract.create/update` | HIGH (migrated) |
| POST `/estimates/{id}/contracts` | contract | org/project tenant + write roles | owner/admin/PM | contract creation | `contract.create` | HIGH (migrated) |
| POST `/contracts/{id}/customer-accept`, `/provider-accept` | contract state | org tenant + party role + version | customer/provider roles | contract activation | `contract.update` | CRITICAL (migrated) |
| POST `/contracts/{id}/payment-intents` | payment | contract tenant + payment roles | owner/admin/PM/customer | payment initiation | `payment.update` | CRITICAL (migrated) |
| POST `/payment-intents/{id}/confirm` | payment state | payment tenant + payment roles + version | owner/admin/PM/customer | payment confirmation | `payment.update` | CRITICAL (migrated) |
| POST `/projects/{id}/maintenance-contracts` | maintenance contract | project tenant + billing rules | owner/admin/PM | recurring contract | `contract.create` | HIGH (migrated) |
| POST `/maintenance-contracts/{id}/cancel` | maintenance state | contract tenant + write roles + version | owner/admin/PM | contract cancellation | `contract.update` | CRITICAL (migrated) |
| POST `/ai-settings` | AI setting | org/project tenant + project-write roles | owner/admin/PM | provider/model/prompt policy | `ai_setting.update` | CRITICAL (migrated) |
| PATCH `/ai-settings/{id}` | AI setting | setting tenant + project-write roles + version | owner/admin/PM | AI configuration change | `ai_setting.update` | CRITICAL (migrated) |
| POST `/artifacts/{id}/upload-intents`; POST `/artifact-versions/{id}/complete-upload` | artifact storage | artifact tenant + artifact-write rules | owner/admin/PM/developer | content upload | legacy | MEDIUM |
| POST `/review-comments/{id}/accept`, `/reject`, `/resolve` | review comment | review tenant + review roles + version | owner/admin/PM/reviewer | review state | legacy | MEDIUM |
| PUT `/memberships/{id}/roles` | organization membership | org admin/owner + `permission.change` + last-owner guard | owner/admin | role escalation/tenant access | `permission.change` | CRITICAL (migrated) |
| POST `/dead-letters/{id}/retry` | worker job | org admin/owner tenant guard | owner/admin | operational retry | legacy | MEDIUM |
| POST `/local/login`, `/logout`, `/switch-organization` | local auth | auth/CSRF flow | n/a | session operation | n/a | NOT_APPLICABLE |
| POST `/payment-webhooks/mock` | test webhook | authenticated test boundary + org check | n/a | test-only provider event | n/a | NOT_APPLICABLE |

The prior 53-action inventory includes the three service-backed mutation
actions represented by the grouped rows above. At the route level, the current
tree exposes 50 mutation routes: 16 are Matrix-enforced, 30 are
`LEGACY_AUTH_ONLY`, and 4 are `NOT_APPLICABLE`; the three service actions remain
covered by the same legacy row and do not introduce an unauthenticated path.
For the release gate, the authoritative counts are `TOTAL=53`,
`MATRIX_ENFORCED=20`, `LEGACY_AUTH_ONLY=29`, `MISSING_AUTH=0`,
`NOT_APPLICABLE=4`.

Risk totals are: `CRITICAL=7`, `HIGH=9`, `MEDIUM=20`, `LOW=17` across the
53-action inventory. Critical/high migration is complete for the 20 listed
Matrix rows. The remaining medium/low (and the explicitly retained legacy
estimate, communication, upload, and worker actions) retain their existing
tenant/role/business guards for the next incremental migration.

Permission changes require `permission.change` and emit an audit event; the
last-organization-owner guard remains in place. AI-agent permissions remain an
empty set, and AI settings cannot be changed through an agent capability.
Existing project, artifact, billing, and resource checks were not removed.

## Test Execution and Completion

Tests ran in an ephemeral PostgreSQL 16 container at
`127.0.0.1:55432/phase1_test`, with no AWS credentials or application DB URL.
The container was non-persistent and was destroyed after verification.

- Security foundation/API tests: 8 passed (rerun)
- Backend regression suite: 202 passed (final full run)
- Backend coverage: 83.05% (final full run; gate threshold passed)
- Security target coverage: 87.02% (8 tests; gate threshold passed)
- Ruff format/check: passed, including undefined-symbol checks
- Secret scan: passed
- pip-audit: no known vulnerabilities
- Migration: upgrade, downgrade, upgrade passed

Bandit 1.8.3 completed on the CI-equivalent Python 3.12.13 runtime. It first
reported one Low B105 false positive for the literal permission identifier
`secret.access`; the line is explicitly marked as a permission identifier, not
a secret. The rerun is clean: High=0, Medium=0, Low=0.

The final verification evidence supports the Phase 1 READY decision. The
remaining legacy medium/low actions are explicitly tracked for the next
incremental matrix migration.

## Future Agent Integration

An Agent executor must receive an explicit capability policy, use
`can_execute_protected_action`, pass an approval ID and target version, and emit
an `ai_agent` audit event for every tool call. No implicit role inheritance or
approval bypass is permitted.

## Future Deployment Gate

Deployment integration should add plan checksum/digest verification, account
and region checks, environment boundaries, destructive-action detection, and a
separate apply approval. This phase intentionally does not implement any of
those operations.
