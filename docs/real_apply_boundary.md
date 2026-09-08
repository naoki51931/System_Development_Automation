# Real Apply Boundary Foundation (Execution Disabled)

## Scope

Step 6A defines the future real Staging apply boundary without connecting to
AWS, Terraform, a remote backend, a database, or a real Staging environment.
The only possible result in this phase is `READY_BUT_DISABLED` or `BLOCKED`.
`DisabledTerraformApplyExecutor` always raises
`REAL_TERRAFORM_APPLY_DISABLED` and contains no subprocess capability.

## Trust boundary

AWS identity evidence is created only by a server-side `AwsIdentityVerifier`.
The API accepts no account, caller ARN, region, state bucket/key, Terraform
root, binary, command, flags, cwd, or plan-path override. The production
verifier is `DisabledAwsIdentityVerifier` until a separately approved
read-only AWS verifier is configured. `FakeAwsIdentityVerifier` is test-only.

Evidence is fresh for ten minutes and binds organization, project, plan ID,
DeploymentPlan SHA, saved-plan SHA, environment, state bucket/key, region, and
Terraform root. Expected staging identity is account `557604519341`, region
`eu-west-2`, bucket `ai-platform-terraform-state-557604519341`, and key
`system-navigator/staging/terraform.tfstate`. The production key
`cloud-a/prod/terraform.tfstate` is invalid for this boundary.

## Authorization and revalidation

Real apply authorization must remain human-only and use the existing
`deployment.execute` permission, approval expiry/four-eyes checks, superseded
plan denial, cross-tenant checks, and Security Gate revalidation. AI_AGENT is
denied. Plan, approval, artifact, saved-plan, and identity evidence hashes are
rechecked immediately before any future executor handoff.

## Exact saved plan and locking

The only future argv shape is:

```text
terraform apply <server-verified-exact-saved-plan-file>
```

No user flags, re-plan, `-auto-approve`, variable overrides, targets,
replacement flags, refresh options, `-lock=false`, state overrides, or generic
command API are permitted. `build_staging_saved_plan_apply_argv` only builds
the fixed tuple; it does not execute it.

Saved-plan path checks must retain realpath, trusted-root, regular-file,
symlink, traversal, device/inode/size, and SHA protections. Future remote
backend verification must confirm bucket, key, region, and staging root.
Terraform state locking is a required future preflight; application DB locking
is not a substitute. Existing PostgreSQL row locking and partial unique indexes
remain required for application execution concurrency and idempotency.

## Failure and audit model

Known failure, timeout, process loss, credential expiry, lock failure, and
unknown outcome must fail closed. Unknown outcome requires
`MANUAL_RECONCILIATION_REQUIRED`; automatic retry and automatic
`terraform destroy` are prohibited. Rollback requires a separate plan,
approval, and human decision.

Audit evidence may contain identifiers, SHA values, account ID, caller ARN,
region, safe state metadata, root identity, approval/authorizer IDs, decision,
reason, executor type, and timestamps. It must never contain credentials,
tokens, raw state, raw plan, or raw Terraform output.

## Enablement gate

Before real apply can be enabled: AWS read-only identity verification, caller
role, region, remote state, Staging root, prerequisites, saved-plan SHA,
`terraform show` review, Security Gate PASS, human plan review, four-eyes
approval, fresh evidence, state locking, application locking, and explicit
human approval for the actual apply must all be complete. This step satisfies
none of the actual-apply approval requirements.
