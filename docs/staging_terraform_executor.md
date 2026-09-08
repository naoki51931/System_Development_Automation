# Safe Staging Terraform Executor Foundation

## Purpose

This phase prepares an approved staging deployment for a future apply. It does
not invoke Terraform, AWS, a backend, or a staging/production database.

## Trust boundary

`SafeStagingTerraformExecutor` accepts a typed execution context and a stored
`DeploymentPlan`; it does not accept a shell command, raw shell text, or a user
supplied executable path. The context is supplied by a fake/test provider in
this phase. AI agents remain denied by default.

## Validation and preparation

Preparation rereads the artifact, parses JSON, canonicalizes it with the Step 1
sorted-key/compact UTF-8 rule, and recomputes SHA-256. The digest must equal
both the plan and approval evidence. The same check is performed during
authorization and immediately again during preparation to protect the TOCTOU
boundary.

The approval must be approved, unexpired, for `deployment.staging`, the same
organization/project/plan, target version 1, and have a distinct approver.
Superseded plans, missing/unknown state, blocked security gates, dangerous
actions, wrong account/region, and cross-tenant access are blocked. A
`review_required` gate still requires the valid human approval.

Only `staging` is accepted. The default Terraform root allowlist contains
`environment/staging`; callers may provide a narrower explicit allowlist.
Absolute paths, `..`, backslashes, non-canonical paths, and symlink escapes are
rejected when a repository root is configured.

## Execution evidence and lifecycle

The `DeploymentExecution` record stores requester, approval, plan digest,
expected context, correlation ID, authorization result, preparation time, and
sanitized evidence including optional Terraform version metadata. Its reachable
states are `requested`, `validating`, `authorized`, `blocked`, and `prepared`.
`executed_at` is intentionally null.

Repeated preparation of an already prepared execution is idempotent. A second
active request for the same plan returns the existing preparation record. The
database and service checks are intended to be paired with a future transaction
lock/optimistic concurrency control before apply is introduced.

## Read-only Terraform CLI verification

`SafeTerraformCliRunner` is the first Terraform CLI boundary. It resolves the
trusted `terraform` executable, uses only fixed argv for `terraform version` and
`terraform show -json <approved local saved plan>`, runs with `shell=False`, a
fixed workspace cwd, a timeout, bounded output, and a scrubbed environment.
AWS, Google, Azure, ARM, Terraform token, and Terraform CLI config credentials
are not inherited. The runner has no generic command method and no apply or
destroy method.

Before and after `show`, the saved plan is checked as a regular non-symlink
file contained by the approved workspace and its device/inode/size/SHA-256 are
compared. Any mutation returns `SAVED_PLAN_FILE_CHANGED`. Only the selected
`format_version`, `terraform_version`, and resource address/mode/type/name/
actions are returned; raw show JSON and the plan binary are not audit evidence.
The parsed resource changes can be passed to the existing deployment security
gate, so delete/destroy and replace behavior remains fail-closed.

The Step 3 tests create a provider-free empty Terraform plan in a temporary
directory. They do not use any repository Terraform root, backend, state,
provider, AWS credential, or remote network.

## Command construction and artifact materialization

The future command policy remains argv-only. The read-only runner executes only
`terraform version` and `terraform show -json`; there is no apply/destroy,
command concatenation, arbitrary executable, or implicit apply in this phase.
Artifact storage already rejects traversal and local storage keys outside its
tenant prefix. A future materializer must use an owner-only random temporary
file, reject symlinks, and clean it up; no plan contents or secrets are written
to audit logs.

## Audit evidence

The executor emits `deployment.execution.requested`,
`deployment.execution.validation_started`, `deployment.execution.authorized`,
`deployment.execution.blocked`, and `deployment.execution.prepared`. Block
reasons and digests are recorded, never the plan document.

## API

- `POST /api/v1/deployment-plans/{id}/execution-requests`
- `GET /api/v1/deployment-executions/{id}`
- `POST /api/v1/deployment-executions/{id}/prepare`

The API names explicitly describe preparation and do not imply that Terraform
has run.

## Known limitations and future apply step

There is no artifact temp-file materialization, AWS account lookup, state lock,
or apply implementation yet. Those belong to a separately approved phase. The
future apply path must accept only the exact saved plan whose digest was
revalidated immediately before the process starts, with a trusted binary, state
lock, and a second audit/evidence record.
