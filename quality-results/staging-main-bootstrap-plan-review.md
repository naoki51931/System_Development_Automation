# Staging main bootstrap plan review

Date: 2026-08-10 UTC
Implementation commit: `dfab8e499cb9cde6478f19290be3bca6b0c38513`
AWS account / region: `557604519341` / `eu-west-2`
State key: `system-navigator/staging/terraform.tfstate` (no existing state file; zero resources)

## Blockers and remediation

The superseded 86-add plan must not be applied. It exposed two blockers: the frontend container and ALB health path did not consistently use `/login`, and the initial apply would create three desired-count-one runtime services before application database credential registration and migration.

The frontend task health command now requests `/login`, and the frontend ALB target group path is `/login`; backend remains `/health` and the worker keeps `python -m app.workers.health`. The frontend runtime command remains `node server.js`.

`enable_runtime_services` is a boolean whose default and ignored staging tfvars value are `false`. All three `aws_ecs_service` resources and their runtime-dependent alarms are gated by it. Task definitions remain in the bootstrap. Setting the flag to `true` after a successful migration creates backend, worker, and frontend services with their existing desired counts of one. The same main staging state is used; persistent `terraform -target` is prohibited.

## Credential and migration order

- The RDS-managed master Secret is created and rotated by RDS. It is reserved for database administration and the separately approved one-off migration task.
- Terraform creates only the application database Secret container, never a Secret version or application credential value. Backend and worker consume this runtime credential after an operator registers it outside Terraform.
- Before credentials exist, backend and worker cannot start and migration cannot run. Frontend does not require the database but is deliberately held behind the common gate to keep the public runtime closed.
- Migration remains a one-off task definition with `alembic upgrade head`; it is not an ECS service and backend startup does not run migrations.

Required sequence:

1. Apply this reviewed Phase 1 infrastructure plan (separate approval): network, endpoints, S3, RDS, IAM, ECS cluster, ALB, task definitions, migration task definition, CloudWatch; no runtime services.
2. Register the application DB Secret value outside Terraform with human approval.
3. Confirm RDS backup/PITR, run the separately approved migration task, require exit code 0, and verify Alembic head.
4. Plan `enable_runtime_services=true`; require backend/worker/frontend desired count 1 and no destructive or production changes.
5. Separately approve/apply that plan, then check health and smoke tests.

## Saved plan review

Plan: ignored `environment/staging/staging-main-bootstrap.tfplan`
Text rendering: ignored `environment/staging/staging-main-bootstrap-plan.txt`

| Check | Result |
|---|---|
| Add / change / replace / destroy | `73 / 0 / 0 / 0` |
| Data reads | `5` |
| Backend / worker / frontend service creates | `0 / 0 / 0` |
| Runtime-service alarms | `0` |
| Task definitions | `4`: backend, worker, frontend, migration |
| Frontend container / target health | `/login` / `/login` |
| Backend container / target health | `/health` / `/health` |
| NAT gateways / EIPs | `0 / 0` |
| Production-address or production-name changes | `0` |

The plan creates a `10.30.0.0/16` staging VPC with two public, two private application, and two database subnets across `eu-west-2a` and `eu-west-2b`. It creates S3 Gateway plus seven private-DNS Interface endpoints: ECR API, ECR DKR, Logs, Monitoring, Secrets Manager, STS, and KMS. No NAT or EIP is present.

The artifact bucket is the staging-only `system-navigator-staging-artifacts-557604519341` bucket with public access blocking, AES-256 encryption, versioning, TLS-only policy, lifecycle controls, and `prevent_destroy` in configuration.

RDS remains PostgreSQL `db.t4g.small`, 20 GiB `gp3`, Single-AZ, private, encrypted, backup retention 3 days, and deletion protection enabled.

The plan pins backend, worker, and migration to app digest `sha256:29b9f0097affcd432444f001ee951e7d86e7f18668110a130bcd666b3f8b78fe`; frontend is pinned to `sha256:5c2eeeee402293fa783c9a6dd67b6f03dce00b3651ef73d314f773d3371e82dc`. No tag-only or `latest` image is used.

Infrastructure alarms in Phase 1 are ALB 5xx, response time, two unhealthy-target alarms, and RDS CPU/connections/free storage/freeable memory. ECS CPU/memory, running-task, worker-heartbeat, and dead-letter alarms are absent until runtime services are enabled. The existing staging SNS topic is referenced; `info@nagi-neco.com` remains `PendingConfirmation` and requires manual confirmation.

Production changes, replacements, and destroys are zero. No production state, name, VPC, RDS, ECS, ALB, S3, ECR, ACM, Route53, HTTPS listener, NAT, EIP, Budget mutation, or secret value is in the plan.

## Stop conditions

Do not apply this plan without a new human approval. Stop if account or region changes, the saved plan is regenerated, any change/replace/destroy or production change appears, a runtime ECS service appears, a Secret value appears, image digest pinning changes, or RDS leaves the reviewed low-cost configuration. Secret registration, migration, runtime-service plan/apply, ECS deployment, GitHub push, and production changes all require separate approval.

Decision: `READY_FOR_MAIN_STAGING_BOOTSTRAP_APPLY_APPROVAL`.
