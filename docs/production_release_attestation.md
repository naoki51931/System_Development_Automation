# Production release attestation gate

The protected release design has two manually dispatched, `master`-only jobs.
`production-migration-evidence` is the trusted future producer and
`production-release` is the consumer/full-plan job. Both use the GitHub
`production` Environment. Neither workflow applies Terraform or deploys a
service. The producer code exists for a future separately approved execution;
it was not run as part of this remediation.

## Trust chain

1. The producer fixes the current protected `master` SHA, obtains migration and
   read-only verification task facts from AWS APIs/log output, signs the closed
   evidence, self-verifies it, and uploads the fixed
   `production-migration-attestation` artifact. There is no observed-head,
   method, reference, key, or artifact-path input.
2. The consumer checks the producer run through the GitHub API: repository,
   workflow path, branch, release SHA, event, run ID/attempt, completed status,
   and successful conclusion must match. It then downloads only the fixed
   artifact name.
3. The consumer's control-plane checkout is `${{ github.sha }}` and must equal
   the current `origin/master` tip. The immutable release tree is a second
   checkout of that same SHA. Verifier code and trust configuration always run
   from the control-plane checkout, never from caller-selected release content.
4. `scripts/verify_production_migration_attestation.py` loads only
   `config/production_migration_attestation_trust.json`. There is no CLI option
   for a public key or approved key id.
5. Both input JSON schemas are closed, non-null, strictly typed, ASCII/NFC,
   duplicate-key rejecting, and non-finite-number rejecting.
6. The Ed25519-signed migration payload contains the canonical SHA-256 of the
   specific Alembic evidence. The evidence fixes account, region, ECS task and
   task definition/revision, cluster, app digest, release SHA,
   workflow/job/ref, run identity, exit code, expected/observed head, output
   checksum, and timestamp.
7. The verifier securely and atomically writes the sole gitignored Terraform
   handoff in the same consumer job, rejecting symlinks and enforcing mode 0600.
   No test helper can write this path; native tests use a separate fixture root.
8. Freshness is reverified immediately before a full, non-targeted saved plan.
   Metadata binds the release SHA, both image digests, attestation SHA, Alembic
   evidence SHA, verifier receipt, Terraform plan SHA, and change counts. The
   binary plan is AES-256-GCM encrypted with a protected Environment secret
   before upload; plaintext never leaves the runner.

The repository contains the reviewed Production public key only. The private
key must be held by a protected signer, such as an approved GitHub Environment
secret integration or AWS KMS, and must never be committed. Test code uses a
separate fixture key explicitly marked `TEST ONLY / NOT FOR PRODUCTION`.

## Required external GitHub configuration

`GITHUB_PRODUCTION_ENVIRONMENT_CONFIGURATION_REQUIRED`: before any Production
plan, configure the `production` Environment with required reviewers, restrict
deployment branches to protected `master`, and protect signer/material and
Production variables. Required protected material includes the Ed25519 signer,
the AES-256 plan-encryption key, verification role/network/task identities,
digest-pinned app image, and Terraform backend/tfvars. The verification task
definition must first exist from a separately reviewed runtime-disabled
infrastructure apply. Repository code declares `environment: production` but
cannot truthfully assert those UI/API protections are configured.

This is a Production-plan blocker, not a blocker for review of this Draft PR.
The producer alone has `id-token: write`; the consumer has read-only repository
and Actions permissions. All third-party Actions in both trust-path workflows
are pinned to immutable commit SHAs. The consumer has no apply job. A future
apply workflow must decrypt with the protected Environment key and accept only
the reviewed saved plan whose plaintext SHA matches metadata; it must not
generate a fresh plan at apply time.
