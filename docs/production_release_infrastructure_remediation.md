# Production release infrastructure remediation

## Decision

The AI review BLOCKER/HIGH/MEDIUM findings are remediated in code. This is release-infrastructure readiness only. It does not approve a Production deploy, Terraform apply, migration, Production database connection, or external launch.

## Digest and topology contract

Production is fixed to AWS account `557604519341`, region `eu-west-2`, application repository `ai-platform-prod`, and frontend repository `ai-platform-prod-frontend`. These are literal constraints, not comparisons among mutable variables. The provider uses the fixed region and `allowed_account_ids`. Backend, worker, and migration consume the same digest-pinned application URI. Terraform rejects tags, `latest`, malformed/short/uppercase digests, and wrong account, region, or repository.

The existing app ECR repository and Production backend addresses are preserved. A dedicated immutable frontend ECR repository is additive. The frontend has its own 256/512 task definition, service, 30-day log group, port-3000 target group, `/login` health check, and catch-all ALB route. Higher-priority backend routes preserve `/api/*`, `/docs*`, `/openapi.json`, `/health`, and `/static/*` on the backend target group.

## Migration hard gate and attestation trust boundary

Terraform creates only an ECS task definition with `alembic upgrade head`; there is no migration service, `aws_ecs_task`, provisioner, or `local-exec`. Terraform apply therefore cannot execute migration as a side effect.

Runtime rollout defaults off. `enable_release_runtime=true` reaches a `terraform_data` lifecycle precondition before the ECS module and lifecycle preconditions on backend, frontend, and worker services. Missing/empty attestation, digest mismatch, non-zero exit, wrong Alembic head, wrong cluster/task/task-definition boundary, invalid release SHA/timestamp/checksum, or an empty stopped reason makes planning fail with `MIGRATION_SEQUENCE_UNSAFE`. With the gate disabled, the existing backend service address remains present and its desired count is ignored rather than forced to zero. Migration task definition creation remains possible with runtime disabled; Terraform never runs it.

Terraform is the rollout enforcement layer, not proof that a task ran. The protected `production-migration-evidence` producer obtains fixed migration-task and read-only Alembic-verification-task results from AWS APIs and exact machine log output. It fixes account/region/repository/cluster, task and task-definition revisions, release SHA, app digest, STOPPED state and exit zero; no human supplies an observed head, method, or reference. This describes future execution only: this remediation made no AWS request and no Production DB connection.

The canonical attestation schema is version 2 with sorted keys, UTF-8, compact separators, and no insignificant whitespace. It contains release/account/region/task/image/exit/Alembic/GitHub producer identity plus the canonical Alembic evidence SHA, algorithm, and fixed key ID. Checksum and signature are excluded only to avoid self-reference. A checked-in fixed vector records exact input, bytes, SHA-256, public key, signature, and tamper rejection. The verifier uses the single reviewed Ed25519 public key; unsigned, fake, wrong-key, malformed, stale, substituted, or tampered evidence fails closed. The private signer must be an externally configured protected Environment secret or KMS key and is not in the repository.

The consumer control plane starts at `github.sha`, proves that it is the lowercase 40-hex current `origin/master` tip, and separately checks out a release tree at the same SHA. Verifier code and trust configuration always come from the control plane. The consumer validates the successful producer run through GitHub API and binds its run ID/attempt, workflow path, branch, event, repository and release SHA. There is no caller-selected release SHA.

`verified_at` is canonical UTC RFC3339, rejects malformed/future timestamps beyond five minutes of skew, and rejects evidence older than 24 hours. Verification is repeated immediately before the full plan. The handoff is atomically created mode 0600 in the same job, rejects symlinks, is gitignored, and is never downloaded or cached. Test values exist only in an isolated Terraform fixture root and cannot write the live path.

After verification, the same consumer job runs an ordinary full `terraform plan` with the protected Production backend/tfvars and no `-target`. It records add/change/replace/destroy totals and binds release SHA, app/frontend digests, attestation SHA, Alembic evidence SHA and saved-plan SHA-256 in metadata. This workflow deliberately has no apply. Any future apply path must consume only that reviewed saved plan and matching metadata; generating a new plan during apply is prohibited.

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
