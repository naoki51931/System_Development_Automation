# Saved Plan Execution Boundary

## Scope

Step 4 validates the workflow for an approved saved plan with a local fake
executor. It does not start Terraform, call AWS, access remote state, mutate a
filesystem, or change Staging/Production. The real `terraform apply` boundary
is intentionally not implemented.

## Architecture and lifecycle

The server resolves the existing `DeploymentPlan`, `DeploymentExecution`,
`ProtectedApproval`, and verified saved-plan handle. The workflow is:

```text
approved DeploymentPlan
  -> prepared DeploymentExecution
  -> saved-plan verification
  -> execution-time revalidation
  -> execution permission and four-eyes checks
  -> FakeTerraformApplyExecutor
  -> sanitized execution evidence
```

The current lifecycle uses the existing safe states: `prepared` may transition
to exactly one terminal result, `executed`, `failed`, or `blocked`. Other
states are rejected. A terminal result is idempotent and cannot be retried by
the fake executor.

## Permission and approval boundaries

Execution uses the separate `deployment.execute` permission. It is not granted
to viewer, developer, reviewer, project manager, or organization administrator
roles; the existing owner policy is the only current role that includes it.
`AI_AGENT` is denied explicitly and remains deny-by-default.

Plan approval and execution are separate events. Execution rechecks the
organization and project boundary, staging-only model constraints, approval
status and expiry, action and target binding, plan checksum, distinct
approver/four-eyes requirement, and superseded-plan status. The caller must be
human and is not allowed to turn execution into a new approval.

## Hash binding and TOCTOU defense

Execution evidence binds the deployment plan/artifact SHA, approval-linked plan
SHA, saved-plan binary SHA, expected account, region, state identity, and
Terraform root. The saved plan must be a verified regular file under the
trusted root. Its realpath, device, inode, size, and SHA are checked before
execution-time revalidation and again immediately afterward. A mismatch is
blocked as `EXECUTION_PLAN_CHECKSUM_MISMATCH`.

The preparation authorization is deliberately forced to revalidate at the
execution boundary. Prepared or authorized results are not trusted as a
substitute for current approval, plan, context, or gate checks. Tests cover
post-prepare mutation, expiry, supersession, context drift, and gate denial.

## Concurrency and idempotency

The database has partial unique protection for active executions by deployment
plan and by organization/project (the environment is staging-only). The
project/environment protection is introduced by migration `ef45ab67cd89`,
after the existing preparation migration. The request path returns an
existing active execution. Execution takes a database row lock with
`SELECT ... FOR UPDATE`; two sessions attempting the same execution therefore
produce one result, never two fake applies. Terminal results are returned
unchanged on resubmission.

## Failure behavior and evidence

The fake executor can simulate success, failure, timeout, cancellation, and
unknown outcome. Failure and timeout remain failed; unknown outcome is blocked.
No automatic retry occurs. Each result stores only sanitized evidence including
executor type `fake`, identifiers, expected context, hashes, timestamps, result,
reason, correlation ID, and an evidence hash. Raw plan binaries, full show JSON,
credentials, tokens, full environment, and raw Terraform output are not
stored.

Audit events distinguish revalidation, success, failure, blocked, and fake
executor activity. Audit writes use the existing append-only application
policy.

## Real-apply tripwire and future requirements

`SafeTerraformCliRunner` has no apply capability, and the fake executor has no
apply method. The only future command shape is the fixed argv
`terraform apply <exact-saved-plan-file>`; it must not be exposed as a generic
command API and must never accept user flags, binary, cwd, path, or raw shell
input. No re-plan is permitted after approval.

Before real apply is separately approved, the implementation must preserve all
of the following: exact approved plan and binary SHA binding; execution-time
rehash; state/account/region/root revalidation; approval expiry and four-eyes;
superseded-plan denial; production and AI_AGENT hard deny; fixed process
timeout; output redaction; sanitized audit evidence; application and remote
locking; idempotency; post-run evidence; and fail-closed unknown/failure
handling.

## What is not implemented

There is no real Terraform process launch, `terraform apply` or `destroy`, AWS
SDK/CLI/STS call, remote backend/state access, production execution, actual
staging deployment, execution API accepting arbitrary arguments, or automatic
retry. The Fake Executor is a local workflow verification tool only.
