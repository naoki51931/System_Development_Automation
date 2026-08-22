# Production Release Phase 1 Readiness

## Decision

**PRODUCTION_RELEASE_REQUIRES_REMEDIATION**

This evidence records the verified Phase 1 production state for release commit
`17af4910f3901684269339e6abf3b5ef5d9aa750`. It contains operational metadata
only and does not contain credentials or secret values.

## Environment

- AWS account: `557604519341`
- AWS region: `eu-west-2`
- Role: `instanceRoleTerraform`

## Production RDS

- Status: `available`
- Current instance class: `db.t4g.medium`
- Pending instance class: `db.t4g.small`
- Multi-AZ: enabled
- Storage: 50 GiB, `gp2`
- Backup retention: 14 days
- Encryption: enabled
- Deletion protection: enabled
- Network exposure: private

Manual snapshot `ai-platform-prod-pre-100rpm-downsize-20260812-010957` is
`available` and encrypted.

Point-in-time recovery evidence:

- Automated backup is active.
- The automated restore window is valid.
- A null DB instance `EarliestRestorableTime` is a warning only and is not, by
  itself, a failed PITR gate.

## Production ECS

- Desired/running/pending tasks: `1/1/0`
- Rollout: `COMPLETED`
- Target health: healthy
- Task definition: `ai-platform-prod-low-traffic:1`
- CPU: 256 units
- Memory: 512 MiB
- Current image reference: `ai-platform-prod:v4`

The current image reference uses a mutable tag instead of an immutable digest.
This is a deployment blocker represented by `DIGEST_INPUT_UNSUPPORTED`.

## Monitoring and Alerts

All 13 CloudWatch alarms are `OK`:

- ALB: 4
- ECS: 3
- RDS: 6

SNS topic `ai-platform-prod-alerts` has a confirmed subscription for
`info@nagi-neco.com`.

## Staging

Staging state: `STAGING_IDLE_MODE_CONVERGED`.

## Quality Baseline

- Backend tests: 187 passed
- Overall coverage: 82.89%
- Critical coverage: 90.86%
- Frontend tests: 34 passed
- Frontend build: passed
- OpenAPI drift: none
- Ruff: passed
- Ruff format: passed
- Bandit: passed
- pip-audit: 0 known vulnerabilities
- `npm audit --omit=dev`: 0 vulnerabilities
- Secret scan: 0 actionable findings

## Migration

Alembic head: `8d4f2a7c9b11`.

## Internal Deployment Blockers

- `RDS_PENDING_MAINTENANCE`
- `DIGEST_INPUT_UNSUPPORTED`
- `FRONTEND_REPOSITORY_MISSING`
- `MIGRATION_SEQUENCE_UNSAFE`
- `WORKER_REQUIRED`

## External Launch Blockers

- `COGNITO_NOT_WIRED`
- `HTTPS_DNS_NOT_WIRED`
- `AI_PROVIDER_NOT_WIRED`
- `PAYMENT_PROVIDER_NOT_WIRED`
- `EMAIL_PROVIDER_NOT_WIRED`

Phase 1 is not ready for production release until the applicable remediation
and launch integration work is completed.
