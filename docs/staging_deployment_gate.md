# Staging Deployment Gate Foundation

## Purpose

Phase 2 Step 1 establishes a product-owned gate for a future staging
deployment. It records a Terraform `show -json`-compatible plan artifact,
binds its SHA-256 digest to a human approval, and returns an authorization
decision without running Terraform or changing AWS.

The flow is:

`plan metadata + fixture -> artifact storage -> SHA-256 -> security gate ->
ProtectedApproval -> same-plan authorization`

## Deployment Plan and Plan Artifact

`DeploymentPlan` stores tenant/project scope, staging environment, creator and
timestamps, storage key, digest, size, format version, Terraform root/workspace,
state identity, AWS account/region, target environment, summary counts, gate
result, approval ID, supersession, and future execution metadata.

The plan document is canonicalized as sorted, compact UTF-8 JSON and stored via
the existing `ArtifactStorage` abstraction. The database stores metadata, not
the plan payload. Audit events never contain the payload or secret-like values.

## Staging-only Restriction

The model has database checks requiring both `environment` and
`target_environment` to equal `staging`. Plan creation accepts only this
domain. Production is therefore deny-by-default at the API, service, and DB
layers.

## Terraform Plan Parsing

The parser consumes the `resource_changes` shape used by Terraform
`show -json`. It extracts resource address/type/action and computes add,
update, replace, and destroy counts. It also scans structured plan metadata for
environment and dangerous-resource hints without emitting the matched content.

This step uses safe local fixtures. It does not invoke Terraform and does not
connect to a Terraform backend, AWS account, state bucket, or provider.

## Security Gate

The result is one of `pass`, `review_required`, or `blocked` with structured
reason codes. Empty, correctly bound plans can pass; ordinary staging changes
reach `review_required`; dangerous or incorrectly bound plans are blocked.

The gate validates:

- staging environment and expected target environment;
- expected AWS account and region;
- expected Terraform root and non-empty state identity;
- production references;
- Route53/DNS, IAM, secret/Secrets Manager/SSM actions;
- snapshot deletion and all unexpected destroy actions.

Expected account, region, root, and state identity are supplied by the future
deployment controller/check configuration. They are not discovered from an
untrusted plan and are not inferred from AWS during this phase.

## Approval Binding and Four Eyes

The existing `ProtectedApproval` is reused with action `deployment.staging`,
resource type `deployment_plan`, resource ID equal to the plan ID, target
version `1`, and `plan_checksum` equal to the artifact SHA-256. Staging
deployment approvals require a distinct approver. The existing approval API
remains the decision surface; deployment plan approval events additionally
update the plan status and emit deployment-specific audit events.

## Execution Authorization

`evaluate_staging_plan` / `can_execute_staging_plan` only return a decision.
They never call Terraform, AWS, a provider, or a state backend. Authorization
requires all of the following:

- staging and a non-blocked, already-run security gate;
- unchanged plan SHA-256;
- matching AWS account, region, and state identity;
- approved `ProtectedApproval` for this exact plan and checksum;
- unexpired approval and distinct approver;
- plan not superseded;
- explicit `deployment.execute_authorize` permission.

Checksum mismatch, missing/rejected/expired approval, stale state, wrong
account/region, superseded plan, cross-tenant access, and unknown permissions
return false and generate a denial audit event.

## Superseded Plans

Creating a new plan for the same organization/project/staging scope marks
active earlier plans as `superseded` and records `superseded_by_id`. A
superseded plan cannot be authorized even if its approval remains approved.

## Permissions

The Phase 1 deny-by-default Matrix adds:

- `deployment.plan.create`
- `deployment.security_check`
- `deployment.execute_authorize`

Organization owners/admins and project managers receive these permissions under
the existing role model. AI agents receive none. Existing tenant membership,
project membership, role checks, approval checks, and business rules remain in
place.

## Audit Events

The following events are emitted with actor, organization/project context,
plan ID, approval ID where available, digest, environment, result, reason,
request ID, and correlation ID:

- `deployment.plan.created`
- `deployment.plan.security_checked`
- `deployment.plan.approval_requested`
- `deployment.plan.approved`
- `deployment.plan.rejected`
- `deployment.plan.execution_authorized`
- `deployment.plan.execution_denied`

Plan JSON, binary content, secrets, tokens, and credentials are excluded.

## API

- `POST /api/v1/deployment-plans` — create and store a staging plan artifact;
- `GET /api/v1/deployment-plans` — list plans within an organization;
- `GET /api/v1/deployment-plans/{id}` — read plan metadata;
- `POST /api/v1/deployment-plans/{id}/security-check` — run the local gate;
- `POST /api/v1/deployment-plans/{id}/request-approval` — bind approval to the digest;
- `POST /api/v1/deployment-plans/{id}/authorize` — return an execution decision only.

## Tests and Limitations

Tests cover valid staging review, production/wrong account/wrong region/wrong
state, production references, DNS/IAM/secrets/snapshot/destroy detection,
approval absence/rejection/expiry, four eyes, checksum mismatch, supersession,
cross-tenant denial, audit, and Phase 1 agent deny-by-default behavior.

This phase does not run Terraform, apply or destroy resources, access AWS,
access production/staging databases, execute an AI agent, access secrets,
change IAM/DNS, or implement a Terraform executor. The next step must add a
separately reviewed executor that consumes this decision and revalidates the
same digest immediately before any apply.
