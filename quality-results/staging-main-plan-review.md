# Main staging Terraform plan review

Reviewed 2026-08-10 UTC. This review covers plan creation and inspection only. No apply, destroy, RDS migration, ECS deployment, secret-value population, SNS confirmation, ECR/GitHub push, or production change was performed.

## Identity, source, and state

- Git HEAD: `ca3a932dcd582686b7fb1e0b68b540a5984de8c5`
- AWS account: `557604519341`
- Region: `eu-west-2`
- Main staging state key: `system-navigator/staging/terraform.tfstate`
- Prerequisite state key: `system-navigator/staging/prerequisites.tfstate`
- Production state key: `cloud-a/prod/terraform.tfstate`
- Existing main staging resources: 0; no state file existed before this initial plan.
- `terraform init -reconfigure` and `terraform validate`: PASS.
- `terraform.tfvars`, `backend.hcl`, saved plan, and text plan are Git-ignored.

## Plan summary

| Action | Count |
|---|---:|
| Add | 86 |
| Read | 5 |
| Change | 0 |
| Replace | 0 |
| Destroy | 0 |

The five reads are generated IAM/S3 policy documents. All managed-resource actions are create-only. No production resource address or create target appears in the plan. No Budget, ECR, prerequisite IAM role, or prerequisite SNS resource is created or changed.

## Network

- One staging VPC: `10.30.0.0/16`.
- Public subnets: `10.30.0.0/24` in `eu-west-2a`, `10.30.1.0/24` in `eu-west-2b`.
- Private application subnets: `10.30.10.0/24` in `eu-west-2a`, `10.30.11.0/24` in `eu-west-2b`.
- Database subnets: `10.30.20.0/24` in `eu-west-2a`, `10.30.21.0/24` in `eu-west-2b`.
- Internet Gateway and separate public/private route tables are create-only.
- NAT Gateways: 0. Elastic IPs: 0.
- VPC endpoints: S3 Gateway plus seven Interface endpoints: ECR API, ECR DKR, Logs, Monitoring, Secrets Manager, STS, and KMS.
- Every Interface endpoint has Private DNS enabled, uses both private application subnets, and uses the endpoint SG. The SG admits TCP 443 only from `10.30.0.0/16`.

## Artifact S3

- Only `system-navigator-staging-artifacts-557604519341` is created; the production bucket has no action.
- Public Access Block: all four controls enabled.
- AES-256 server-side encryption, versioning, TLS-only bucket policy, 90-day noncurrent-version lifecycle, and 7-day incomplete-upload cleanup are configured.
- `force_destroy = false` and Terraform `prevent_destroy = true`.

## RDS and database secrets

- PostgreSQL 17, `db.t4g.small`, 20 GB allocated gp3, Single-AZ.
- Private database subnets only; `publicly_accessible = false`.
- Encryption, three-day backup retention, final snapshot, and deletion protection are enabled.
- RDS manages its master password in Secrets Manager; no password or secret value is present in configuration or plan.
- The staging security module creates only `/system-navigator/staging/database`; no Cognito, Stripe, email, or AI provider Secret container is planned.
- RDS storage autoscaling has a 100 GB maximum, but initial allocated storage is exactly 20 GB. It is not planned as 30/50 GB, Multi-AZ, or `db.t4g.medium`.

## ECS and images

- Cluster: `system-navigator-staging-cluster`.
- Separate execution, backend, worker, frontend, and migration task roles.
- Four task definitions: backend, worker, frontend, migration. Only backend, worker, and frontend are services, each desired count 1. Migration is one-off only.
- Backend/worker/migration image: `557604519341.dkr.ecr.eu-west-2.amazonaws.com/system-navigator-staging-app@sha256:29b9f0097affcd432444f001ee951e7d86e7f18668110a130bcd666b3f8b78fe`.
- Frontend image: `557604519341.dkr.ecr.eu-west-2.amazonaws.com/system-navigator-staging-frontend@sha256:5c2eeeee402293fa783c9a6dd67b6f03dce00b3651ef73d314f773d3371e82dc`.
- Both registry digests exist in ECR. No runtime image uses `latest` or a tag-only reference.
- Commands match the design: backend `uvicorn app.main:app --host 0.0.0.0 --port 8000`; worker `python -m app.workers.runner`; frontend `node server.js`; migration `alembic upgrade head`.
- `APP_ENV=staging`, LocalAuth false, and mock AI/payment/email true.

## IAM

- Execution role has the AWS ECS execution policy plus GetSecretValue restricted to planned database Secret ARNs.
- Backend has GetSecretValue for application database inputs only.
- Worker has the same secret read plus object/list operations restricted to the staging artifact bucket.
- Migration has GetSecretValue restricted to the RDS-managed database secret.
- Frontend has no inline task policy and receives no database Secret, S3 permission, or Secrets Manager permission.
- No AdministratorAccess or wildcard AWS administration policy is planned.

## ALB and security

- One internet-facing staging ALB and one HTTP port 80 listener. No HTTPS listener, ACM certificate, or Route53 record.
- No `true-camera-test` reference exists in the plan.
- ALB ingress is TCP 80 from the internet. Backend port 8000 and frontend port 3000 accept traffic from the ALB SG; PostgreSQL 5432 accepts traffic from the application task SG. No SSH ingress is planned.
- This HTTP-only endpoint is temporary staging only: no customer use, real authentication, real payment, sensitive data, or production use.

## Health and monitoring

- Backend ALB/container health uses `/health`.
- Worker container health uses `python -m app.workers.health`.
- Frontend ALB/container health currently uses `/`, not the required `/login`; this is an apply-readiness blocker.
- Four log groups—backend, worker, frontend, migration—use 14-day retention.
- Eighteen alarms cover ALB 5xx/response time/unhealthy targets, ECS CPU/memory, backend/worker running tasks, worker heartbeat, dead-letter growth, and RDS CPU/connections/free storage/freeable memory.
- Every alarm references `arn:aws:sns:eu-west-2:557604519341:system-navigator-staging-alerts`.

## Prerequisites, SNS, and Budget

- Both ECR repositories and image digests, the GitHub staging deploy role, SNS topic, and Budget were confirmed read-only in AWS.
- Budget `system-navigator-staging-monthly` remains 150 USD/month and has no main-plan action.
- SNS email `info@nagi-neco.com` remains `PendingConfirmation` (0 confirmed, 1 pending).
- `MANUAL_SNS_CONFIRMATION_REQUIRED`; this alone does not fail the plan.

## Production impact and cost

- Production changes: 0. No production VPC, RDS, ECS, ALB, S3, ECR, state, or other resource is targeted.
- Persistent/hourly cost sources: RDS, ALB, three Fargate services, seven Interface VPC endpoints, S3 storage/requests, CloudWatch Logs/metrics, and Secrets Manager. NAT cost is avoided; Interface endpoints still incur endpoint-hour and data-processing charges.

## Apply blockers and migration sequence

The plan is structurally add-only, but it is not ready for apply:

1. Frontend ALB and container health checks use `/` instead of the required `/login`.
2. The initial apply plans backend and worker services at desired count 1 while their application database Secret is created without a Secret value. The plan also does not enforce migration completion before service startup. An approved bootstrap design must keep services stopped or otherwise populate the database connection Secret through a separately approved process before service launch.

Required later sequence, under separate approvals:

1. Apply main staging infrastructure with application services safely held.
2. Wait for RDS readiness.
3. Confirm snapshot/backup protection.
4. Populate required database connection material through the approved secret procedure.
5. Run the migration task.
6. Confirm migration exit code 0.
7. Start backend, worker, and frontend.

Apply must stop if a revised plan contains any destroy, replace, production action, NAT/EIP, custom-domain resource, tag-only image, weakened RDS protection, enabled LocalAuth/real provider, or broadened IAM permission.

## Gate decision

| Gate | Result |
|---|---|
| BACKEND_CONFIRMED | PASS |
| STATE_ISOLATED | PASS |
| PREREQUISITES_CONFIRMED | PASS |
| PLAN_CREATED | PASS |
| ADD_ONLY | PASS |
| DESTROY_ZERO | PASS |
| REPLACE_ZERO | PASS |
| PRODUCTION_CHANGES_ZERO | PASS |
| NETWORK_SCOPE | PASS |
| NAT_ZERO | PASS |
| EIP_ZERO | PASS |
| ENDPOINT_SCOPE | PASS |
| S3_SCOPE | PASS |
| RDS_SCOPE | PASS |
| RDS_LOW_COST_CONFIG | PASS |
| ECS_SCOPE | FAIL — startup order is not safely gated |
| IMAGE_DIGEST_PINNING | PASS |
| TASK_ROLE_SCOPE | PASS |
| ALB_SCOPE | PASS |
| CUSTOM_DOMAIN_DISABLED | PASS |
| MONITORING_SCOPE | FAIL — frontend health path differs from `/login` |
| SNS_TOPIC_REFERENCE | PASS |
| BUDGET_UNCHANGED | PASS |
| LOCAL_AUTH_DISABLED | PASS |
| MOCK_PROVIDER_CONFIG | PASS |

Final decision: `NOT_READY_FOR_MAIN_STAGING_APPLY_APPROVAL`.
