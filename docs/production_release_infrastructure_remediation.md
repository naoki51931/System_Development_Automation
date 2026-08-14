# Production release infrastructure remediation

## Decision

The four infrastructure blockers are remediated in code: `DIGEST_INPUT_UNSUPPORTED`, `FRONTEND_REPOSITORY_MISSING`, `MIGRATION_SEQUENCE_UNSAFE`, and `WORKER_REQUIRED`. This is release-infrastructure readiness only. It does not approve a Production deploy or external launch.

## Digest and topology contract

`app_image_uri` must be the exact `${account}.dkr.ecr.${region}.amazonaws.com/${name}@sha256:${64-lowercase-hex}` URI. Backend, worker, and migration consume that identical value. `frontend_image_uri` has the same contract for `${name}-frontend`. Terraform rejects mutable tags, `latest`, malformed or uppercase digests, and the wrong account, region, or repository.

The existing app ECR repository and Production backend addresses are preserved. A dedicated immutable frontend ECR repository is additive. The frontend has its own 256/512 task definition, service, 30-day log group, port-3000 target group, `/login` health check, and catch-all ALB route. Higher-priority backend routes preserve `/api/*`, `/docs*`, `/openapi.json`, `/health`, and `/static/*` on the backend target group.

## Migration ordering

Terraform creates only an ECS task definition with `alembic upgrade head`; there is no migration service, `aws_ecs_task`, provisioner, or `local-exec`. Terraform apply therefore cannot execute migration as a side effect.

Runtime rollout defaults off. After a separately approved one-off task succeeds with exit zero and Alembic head is verified, an operator may set `migration_succeeded_app_image_uri` to the exact reviewed app digest. `enable_release_runtime=true` fails with `MIGRATION_SEQUENCE_UNSAFE` unless the two full URIs match.

## Worker and monitoring

The independent worker task and service use the implemented `python -m app.workers.runner` command, the shared app digest, 256 CPU, 512 MiB, desired count one, private subnets, and no public IP. Release monitoring adds frontend/worker running-task alarms plus worker CPU, `WorkerHeartbeatAgeSeconds`, and `DeadLetterCount` alarms. These alarms are gated with the runtime and use the isolated Production SNS topic.

## Fail-closed boundaries

Production runtime fixes `APP_LOCAL_AUTH_ENABLED`, mock-provider flags, Cognito, Stripe, and SES to false. `external_launch_ready` is validation-forced false. Cognito, HTTPS/DNS, AI, payment, and email remain unconnected and require separate work and approval.

No Production RDS/NAT/ALB/backend address was renamed or moved. The legacy backend task definitions stay registered for rollback, and the existing service points to them until the migration gate is satisfied. Staging IDLE code was not changed, and active release configuration has zero `true-camera-test.com` references.

## Prohibited operations observed

No AWS write, Terraform apply/destroy, ECR push, migration, Production DB connection, secret change, ECS deployment, RDS change, force push, merge, or direct master change was performed. Backend tests used a new local PostgreSQL database only.
