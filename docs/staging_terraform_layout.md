# Staging Terraform layout and controls

## Layout and state

`environment/` is the legacy production root. It retains `cloud-a/prod/terraform.tfstate`, `ai-platform-prod`, and all current Terraform addresses. It is intentionally not moved into a new directory because that would invite an unnecessary state migration.

`environment/staging/` is an independent root. Its committed `backend.hcl.example` uses `system-navigator/staging/terraform.tfstate`; real `backend.hcl` is ignored. It calls only additive `modules/staging_network`, `staging_storage`, `staging_database`, `staging_security`, `staging_ecs`, and `staging_monitoring`. There are no `moved` or import blocks.

## Isolation and naming

Staging uses prefix `system-navigator-staging` for VPC, subnets, NAT, ALB, ECS cluster/services/tasks, RDS, IAM, SNS, and alarms. Log groups are `/system-navigator/staging/{backend,worker,frontend,migration}`. Empty secret containers are `/system-navigator/staging/{database,cognito,stripe,email,ai/openai,ai/anthropic}`. The distinct RDS master secret is generated and managed by RDS. Production RDS, S3, Secrets, Cognito, ECS, ALB, logs, DNS, and provider configuration are never inputs to staging.

The default is a staging-only VPC. Setting `create_vpc=false` requires an existing VPC and at least two private and two public subnet IDs; supplying both modes fails validation. The selected initial dedicated VPC uses no NAT and explicit endpoints because 4/5 EIPs are already allocated; one NAT would consume the final EIP. A shared VPC is permitted only after network review.

## Workloads and least privilege

Backend, worker, frontend, and migration have separate task roles and task definitions; execution has a separate execution role. Frontend gets no S3 or secret task permission. Backend reads runtime secrets. Worker reads runtime secrets and, when enabled, the staging artifact bucket. Migration reads only the RDS-managed master database secret. The GitHub staging role trusts only the repository's `staging` environment and has scoped ECS/pass-role permissions; no AdministratorAccess policy exists.

Backend runs `uvicorn app.main:app --host 0.0.0.0 --port 8000`, worker runs `python -m app.workers.runner`, frontend runs `node server.js`, and migration runs `alembic upgrade head`. Health checks cover backend `/health`, frontend `/login`, and `python -m app.workers.health`. Backend and frontend have separate target groups; backend/worker also register in a private service-discovery namespace.

The backend and worker Cloud Map services use DNS configuration only. An empty `health_check_custom_config {}` was removed because AWS/provider refresh omitted it and repeatedly proposed ForceNew replacement of both existing services. Custom health checks are not required before runtime services exist; no `lifecycle.ignore_changes` workaround is used. The resulting reconcile plan keeps both discovery resources as no-op.

`enable_runtime_services` defaults to `false`. Phase 1 creates network, endpoints, S3, RDS, the empty application database Secret container, IAM, ECS cluster, ALB, all task definitions, and infrastructure alarms, but creates no backend, worker, or frontend service and no runtime-service alarms. Phase 2 is a separately approved, non-Terraform registration of the application database Secret value. The RDS-managed master Secret is reserved for administration and the one-off migration task; the application database Secret is the runtime backend/worker credential. Frontend has no database dependency but shares the gate so no public runtime starts early. Before either Secret is available, backend, worker, and migration cannot run; frontend is intentionally held for deployment-order consistency.

After RDS is ready and backup/PITR protection is confirmed, Phase 3 runs the separately approved one-off migration task, checks exit code 0 and Alembic head, and performs no automatic backend migration. Phase 4 plans `enable_runtime_services=true` with desired counts of one; Phase 5 applies that reviewed service-only addition and verifies health and smoke tests. The same main staging state is used throughout; routine `terraform -target` is prohibited.

## Providers, secrets, and HTTPS

Mock AI/payment/email default to true and must be shown clearly in the UI during testing. Cognito, Stripe, and SES default off. Cognito inputs are pool/client/issuer/domain; Stripe accepts secret ARNs, a publishable test key, and an HTTPS webhook endpoint; SES requires Sandbox, region, from address, and configuration set. Live Stripe mode and LocalAuth fail validation, and application startup refuses LocalAuth in staging/production.

Terraform never stores application secret values in code. Populate secret versions only through the separately approved secret-registration runbook, then record version ARNs without logging values. No SystemNavigator AI resource uses `true-camera-test.com`; no replacement domain is selected. `enable_custom_domain=false` disables ACM, Route53 records and HTTPS. Temporary staging checks use the ALB HTTP DNS name only and are prohibited for production, customers, Stripe/Cognito/real authentication, or sensitive data. A newly approved domain can later re-enable ACM DNS validation, HTTPS 443, and HTTP-to-HTTPS redirect.

## Data, migration, monitoring, and rollback

Staging RDS is PostgreSQL, private, encrypted, Single-AZ by default, deletion-protected, and backed up for seven days. The artifact bucket is unique, versioned, encrypted, public-blocked, TLS-only, lifecycle-managed, and has origin-minimized CORS. Migration and application database users are separated operationally: migration gets DDL for the approved task window; the app gets runtime DML only.

Monitoring defines ECS CPU/memory, ALB 5xx/unhealthy targets, RDS CPU/connections/storage, worker heartbeat, dead-letter growth, SNS notification, and a tag-filtered monthly budget. Before production-like testing, verify the application emits the two custom worker metrics.

The approved recipient is `info@nagi-neco.com`, supplied only by ignored tfvars. ALB alarms cover five 5xx in five minutes, unhealthy targets, and p95 response time above two seconds for five minutes. ECS alarms cover CPU/memory above 80% for five minutes and backend/worker running task deficits through Container Insights. Worker heartbeat missing/older than 120 seconds and any dead letter alert immediately. RDS covers CPU, connections (default 80), free storage below 5 GiB, and freeable memory below 256 MiB; instance-sensitive thresholds are variables. CloudWatch uses the staging SNS topic; Budget uses direct email for actual 50/80/100% and forecasted 100% of 100 GBP.

The SNS email subscription is not auto-confirmed and remains `PendingConfirmation` until a human accepts AWS's confirmation message. `info@nagi-neco.com` is not an application customer-mail destination. Initial staging keeps MockEmailProvider enabled and SES outbound/inbound disabled; MX changes, receiving S3, and Inbox API are rejected initial designs.

Rollback selects previous immutable ECS task definitions, stops workers if schema compatibility is uncertain, and prefers a forward fix. A database restore creates a new instance from the verified snapshot; it never overwrites the old RDS. Preserve S3 versions, Secrets versions, logs, and audit evidence.

## Validation and approval boundaries

Allowed static workflow: `terraform fmt -recursive`, `terraform init -backend=false`, `terraform validate`, and local tests. Run production and staging roots separately. Before a plan, supply reviewed account ID, repositories/digests, unique bucket, production comparison names, OIDC provider ARN, network inputs, notification destination, and—if enabled—ACM/DNS/Cognito/Stripe/SES inputs.

Real AWS IDs, resource existence, quotas, IAM permissions, AZ/subnet capacity, ECR image presence, certificate/zone ownership, RDS engine availability, prices, alarm delivery, custom metric emission, and provider credentials remain unverified. Read-only AWS discovery requires human approval. Terraform plan, apply, secret registration, migration, ECS/ECR, DNS, Cognito, Stripe, and SES each remain separately approved actions.

## Pre-plan bootstrap and digest contract

`environment/staging-prerequisites` is an independently reviewed state owning the two ECR repositories, GitHub staging deploy role/policy, staging SNS subscription, and 100 GBP Budget. Conditional ACM and validation resources have count zero while custom domains are disabled. Its key is `system-navigator/staging/prerequisites.tfstate`; it contains no VPC, subnet, endpoint, RDS, ECS, ALB, artifact S3, or Secret. After approved push, main staging consumes full ECR `repository@sha256:...` values; backend and worker share a digest.

The dedicated VPC has two public, two private application, and two isolated database subnets. The default avoids a fifth EIP/NAT and creates private ECR API/DKR, S3, Logs, Monitoring, Secrets Manager, STS, and KMS endpoints. DNS and HTTPS remain absent until a new domain receives separate approval.

Apply ordering is dependency-driven without permanent `-target`: prerequisites produces ECR URLs, deploy-role ARN, and SNS topic ARN. Operators copy reviewed outputs into ignored main tfvars. Main staging then creates network/storage/security, RDS/ECS/ALB and CloudWatch alarms, outputting the ALB DNS name. Prerequisites never reads main state; dependency is one-way. Image push/digest capture and any future domain/HTTPS activation remain separate approval boundaries.
