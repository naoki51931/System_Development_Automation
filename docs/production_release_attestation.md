# Production release attestation gate

The `production-release` workflow is a preparation gate only. It performs no
Terraform apply, deployment, migration, or database connection. The
`production-plan` job is bound to the GitHub `production` Environment and runs
only from manual dispatch on `master`.

## Trust chain

1. The workflow downloads the fixed `production-migration-attestation`
   artifact from a same-repository run. Callers cannot submit a raw attestation.
2. `scripts/verify_production_migration_attestation.py` loads only
   `config/production_migration_attestation_trust.json`. There is no CLI option
   for a public key or approved key id.
3. Both input JSON schemas are closed, non-null, strictly typed, ASCII/NFC,
   duplicate-key rejecting, and non-finite-number rejecting.
4. The Ed25519-signed migration payload contains the canonical SHA-256 of the
   specific Alembic evidence. The evidence fixes account, region, ECS task and
   task definition, release SHA, workflow/job/ref, run identity, exit code,
   expected/observed head, output checksum, and timestamp.
5. The verifier writes the only Terraform input to the fixed, gitignored
   `environment/.production-release/verified-attestation.json` path. Terraform
   has no raw object or configurable file-path variable.
6. Terraform rechecks release identity and both attestation/handoff freshness
   (24-hour maximum age, five-minute future skew) immediately before plan.

The repository contains the reviewed Production public key only. The private
key must be held by a protected signer, such as an approved GitHub Environment
secret integration or AWS KMS, and must never be committed. Test code uses a
separate fixture key explicitly marked `TEST ONLY / NOT FOR PRODUCTION`.

## Required external GitHub configuration

`GITHUB_PRODUCTION_ENVIRONMENT_CONFIGURATION_REQUIRED`: before any Production
plan, configure the `production` Environment with required reviewers, restrict
deployment branches to protected `master`, and protect signer/material and
Production variables. Repository code declares `environment: production` but
cannot truthfully assert those UI/API protections are configured.

This is a Production-plan blocker, not a blocker for review of this Draft PR.
The workflow deliberately has no `id-token: write` and no apply step.
