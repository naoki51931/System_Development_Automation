# Production release infrastructure remediation

## Decision

The AI review BLOCKER/HIGH/MEDIUM findings are remediated in code. This is release-infrastructure readiness only. It does not approve a Production deploy, Terraform apply, migration, Production database connection, or external launch.

## Digest and topology contract

Production is fixed to AWS account `557604519341`, region `eu-west-2`, application repository `ai-platform-prod`, and frontend repository `ai-platform-prod-frontend`. These are literal constraints, not comparisons among mutable variables. The provider uses the fixed region and `allowed_account_ids`. Backend, worker, and migration consume the same digest-pinned application URI. Terraform rejects tags, `latest`, malformed/short/uppercase digests, and wrong account, region, or repository.

The existing app ECR repository and Production backend addresses are preserved. A dedicated immutable frontend ECR repository is additive. The frontend has its own 256/512 task definition, service, 30-day log group, port-3000 target group, `/login` health check, and catch-all ALB route. Higher-priority backend routes preserve `/api/*`, `/docs*`, `/openapi.json`, `/health`, and `/static/*` on the backend target group.

## Migration hard gate and attestation trust boundary

Terraform creates only an ECS task definition with `alembic upgrade head`; there is no migration service, `aws_ecs_task`, provisioner, or `local-exec`. Terraform apply therefore cannot execute migration as a side effect.

Runtime rollout defaults off. `enable_release_runtime=true` reaches a `terraform_data` lifecycle precondition before the ECS module and lifecycle preconditions on backend, frontend, and worker services. Missing/empty attestation, digest mismatch, non-zero exit, wrong Alembic head, wrong cluster/task/task-definition boundary, invalid release SHA/timestamp/checksum, or an empty stopped reason makes planning fail with `MIGRATION_SEQUENCE_UNSAFE`. With the gate disabled, the existing backend service address remains present and its desired count is ignored rather than forced to zero. Migration task definition creation remains possible with runtime disabled; Terraform never runs it.

Terraform is the rollout enforcement layer, not proof that a task ran. `scripts/verify_production_migration_attestation.py` is the external read-only proof layer. It calls only ECS `DescribeTasks` and `DescribeTaskDefinition` and verifies the fixed account/region/repository/cluster, exact task-definition revision, migration container and command, STOPPED state, stopped reason, essential exit code zero, and ECS-resolved digest.

The canonical JSON schema is version 1 with sorted keys, UTF-8, compact separators, and no insignificant whitespace. It contains `schema_version`, release SHA, account/region, ECS cluster/task/task-definition ARN and revision, app URI/resolved digest, container/exit/stopped fields, expected/verified Alembic head, verification method/reference, UTC timestamp, GitHub repository/workflow/run/attempt/job/SHA/ref, `signature_algorithm`, `signing_key_id`, `artifact_sha256`, and `artifact_signature`. The checksum and signature are excluded from the signed/hash payload to avoid self-reference. The verifier recomputes SHA-256 over the canonical payload and verifies an Ed25519 signature against a trusted public-key mapping; unsigned, unknown-key, invalid-signature, unsupported-schema, and tampered artifacts fail closed. No KMS key is created or implicitly reused by this change; the protected release workflow supplies the approved public-key contract.

The approved release workflow must use the post-merge Production release commit SHA, not the PR branch SHA. The verifier requires `release_sha == approved_release_sha == github_sha`, the fixed repository/workflow/job identity, a non-empty workflow run/attempt, and a `refs/heads/*` ref. Terraform also requires the attestation release SHA to equal the separately supplied approved release SHA; it cannot be changed by changing the image digest alone.

`verified_at` is UTC RFC3339, rejects malformed/future timestamps beyond five minutes of clock skew, and rejects artifacts older than 24 hours. The verifier requires an allowlisted Alembic verification method and non-empty verification reference. It does not connect to Production PostgreSQL: the approved sequence is migration task exit 0, separately approved read-only `alembic current` verification, canonical artifact generation, checksum, signature, signature verification, protected immutable artifact handoff, then fresh Terraform plan. Terraform consumes only the verified artifact fields and does not treat a free `verified=true` flag as proof. Artifacts are stored outside Git (protected workflow artifact/versioned object or a local file covered by checksum/signature); repository copies are ignored.

The verifier deliberately does not connect to Production PostgreSQL. After the separately approved migration task, a separately approved Production DB verification step must execute `alembic current` through the approved migration-task network/role path, record that the sole current revision is `8d4f2a7c9b11`, and obtain human release approval. No direct operator workstation/RDS connection is authorized by this runbook. Pass that approved revision to `--verified-alembic-head`; then run the read-only verifier and archive its JSON in the controlled release evidence store. Only after review of that artifact may its fields be supplied to a fresh Terraform plan. This repository change performed none of those Production operations.

## Worker and monitoring

The independent worker task and service use `python -m app.workers.runner`, the shared app digest, 256 CPU, 512 MiB, desired count one, private subnets, and no public IP. It emits `WorkerHeartbeatAgeSeconds` and `DeadLetterCount` through CloudWatch `PutMetricData` in `SystemNavigator/Production`, with `Environment=production` and `ServiceName=ai-platform-prod-worker`, exactly matching the alarms. Only the worker task role receives `cloudwatch:PutMetricData`, constrained by the CloudWatch namespace condition. Emission errors produce the constant `WORKER_METRIC_EMISSION_FAILED` log event without SDK exception text and do not terminate job processing.

Release monitoring adds frontend/worker running-task alarms, worker CPU, worker `AWS/ECS MemoryUtilization` at 80% for two five-minute periods, heartbeat age, and dead-letter count alarms, all connected to the isolated Production SNS topic. `DeadLetterCount` is a gauge and the alarm uses `Maximum`.

## Frontend image retention

The dedicated frontend ECR repository keeps immutable tags, scan-on-push, and explicit AES256 encryption. Its lifecycle policy retains the newest 20 tagged release images for rollback and removes untagged images only after seven days. The release process must keep immutable tags named `release-<gitsha>` on the current and selected rollback digests; a current or rollback digest must never be left untagged. The seven-day untagged grace prevents immediate cleanup but is not a substitute for release tags.

## Fail-closed boundaries

Production runtime fixes `APP_LOCAL_AUTH_ENABLED`, mock-provider flags, Cognito, Stripe, and SES to false. `external_launch_ready` is validation-forced false. Cognito, HTTPS/DNS, AI, payment, and email remain unconnected and require separate work and approval.

No Production RDS/NAT/ALB/backend address was renamed or moved. The legacy backend task definitions stay registered for rollback, and the existing service points to them until the migration gate is satisfied. Staging IDLE code was not changed, and active release configuration has zero `true-camera-test.com` references.

Frontend/backend/worker/migration continue to share the existing application security group. Splitting it safely would require live state/plan evidence about the existing backend, ALB, and RDS relationships. That evidence is outside this no-AWS-change remediation, so `FOLLOW_UP_SECURITY_HARDENING` remains open rather than risking backend replacement or unsafe state migration.

External blockers remain unresolved: `COGNITO_NOT_WIRED`, `HTTPS_DNS_NOT_WIRED`, `AI_PROVIDER_NOT_WIRED`, `PAYMENT_PROVIDER_NOT_WIRED`, and `EMAIL_PROVIDER_NOT_WIRED`. `RDS_PENDING_MAINTENANCE` also remains unresolved because no live read-only AWS verification was performed in this remediation.

## Prohibited operations observed

No AWS write, Terraform apply/destroy, ECR push, migration, Production DB connection, secret change, ECS deployment, RDS change, force push, merge, or direct master change was performed. Backend tests used a new local PostgreSQL database only.
