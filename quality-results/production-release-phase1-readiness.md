# Production Release Phase 1 readiness

Collected 2026-08-13 from `origin/master` at release SHA `17af4910f3901684269339e6abf3b5ef5d9aa750`. PR #2 head `76d48e305b57b6b51511fd25c8bf3e660c3b018c` and merge commit `17af4910f3901684269339e6abf3b5ef5d9aa750` are both ancestors of `origin/master`. Work used detached clean tree `/tmp/ai-platform-production-release-17af491`; evidence is committed only on `agent/production-release`.

## Gate results

- AWS: account `557604519341`, effective IMDS region `eu-west-2`, assumed role `instanceRoleTerraform`.
- RDS: `available`, PostgreSQL 18.3, `db.t4g.medium`, pending `db.t4g.small`, Multi-AZ, 50 GiB gp2, retention 14, deletion protection/encryption enabled, private. Classification: `RDS_DOWNSIZING_STILL_PENDING_MAINTENANCE`; migration/deployment remain prohibited.
- PITR: PASS with allowed null DB-instance earliest warning. Automated backup/resource ID/restore window and encrypted automated snapshot passed. Manual snapshot `ai-platform-prod-pre-100rpm-downsize-20260812-010957` is available and encrypted.
- Monitoring: 13/13 alarms (ALB 4, ECS 3, RDS 6), all OK; `ai-platform-prod-alerts` email subscription for `info@nagi-neco.com` is confirmed.
- ECS: `ai-platform-prod-low-traffic:1`, CPU 256, memory 512 MiB, desired/running/pending 1/1/0, rollout COMPLETED, target healthy. GET `/`, `/health`, `/docs` returned 200.
- Staging idle: RDS 0, ALB 0, Interface Endpoint 0, runtime ECS cluster/service inventory 0. No Staging action was performed.
- Backend: 187 tests passed; overall 82.89%; critical services 90.86%. Ruff format/lint/undefined symbols, compileall, Bandit, pip-audit (zero known vulnerabilities), secret scan and PITR unit tests passed. Alembic has one head: `8d4f2a7c9b11`.
- Frontend: 34 tests passed; typecheck and Production build passed; OpenAPI generated hash unchanged; `npm audit --omit=dev` reports 0 vulnerabilities. An additional Production-baked LocalAuth coverage invocation had 33 pass/1 fail and is recorded as a non-required configuration-context failure; the required `npm test` passed.
- Images built locally with full SHA tags. Backend local ID `sha256:8806018c8b50163d13a7c1c06d8706424301feb1045a72a969af57f48e271e59`; frontend local ID `sha256:f00bc2ed90b47f5ecf9c14dd583cd73bf2cde4a91b4b883b78fa762817342524`. Both are non-root. Backend runtime has no pip/pytest/Ruff/Bandit/pip-audit. Frontend is standalone, runs `node server.js`, does not require `public/`, and `/login` returned 200 locally. These IDs are not registry digests.

## Blocking review

Production ECR inventory has only `ai-platform-prod` for the backend. No Production frontend repository exists. The repository is immutable, scan-on-push enabled, AES256 encrypted, but the missing frontend repository makes the push gate fail closed. No image was pushed and no registry scan/digest exists.

Production Terraform accepts `container_image_tag` and constructs a single backend image; it cannot accept a `repository@sha256:...` digest and has no frontend, worker, or migration task/service. Real ignored `environment/backend.hcl` and `environment/terraform.tfvars` are absent in this fresh management checkout; only examples exist, and the backend example has the correct Production key but an obsolete example region. Consequently tfvars were not synthesized, Terraform init was not run, and no plan was created.

The release requires schema head `8d4f2a7c9b11`. Production has no migration task/order and no independent worker despite runtime handlers for outbox, notification, email, document, AI workflow, maintenance and expiration. Classification: `PRODUCTION_RELEASE_SEQUENCE_UNSAFE` and `WORKER_REQUIRED_BEFORE_PRODUCTION_RELEASE`. LocalAuth is forced off, but Cognito, HTTPS/DNS and real AI/payment/email providers are not wired: these block external launch; missing migration/worker and digest-capable runtime topology block internal deployment.

## Decision

`MASTER_MERGE_CONFIRMED`, `PRODUCTION_RELEASE_SHA_FIXED`, `PITR_READY`, `MONITORING_READY`, `BACKEND_QUALITY_PASS`, and required `FRONTEND_QUALITY_PASS` are true. `PRODUCTION_RDS_READY`, image push/scan/digest gates, plan gates, migration sequence safety and worker readiness are false. Final decision: **PRODUCTION_RELEASE_REQUIRES_REMEDIATION**.

Next exact approval: authorize a separate remediation branch/PR to add immutable Production backend/frontend digest inputs and repositories, migration-before-runtime task sequencing, and an explicitly sized Production worker; preserve the existing state key/addresses and require a new Phase 1 run after RDS maintenance completes. No Terraform apply, migration, deployment, Secret/RDS/service change, or GitHub push occurred.
