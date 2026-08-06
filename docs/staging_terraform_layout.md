# Staging Terraform layout and controls

## Layout and state

`environment/` is the legacy production root. It retains `cloud-a/prod/terraform.tfstate`, `ai-platform-prod`, and all current Terraform addresses. It is intentionally not moved into a new directory because that would invite an unnecessary state migration.

`environment/staging/` is an independent root. Its committed `backend.hcl.example` uses `system-navigator/staging/terraform.tfstate`; real `backend.hcl` is ignored. It calls only additive `modules/staging_network`, `staging_storage`, `staging_database`, `staging_security`, `staging_ecs`, and `staging_monitoring`. There are no `moved` or import blocks.

## Isolation and naming

Staging uses prefix `system-navigator-staging` for VPC, subnets, NAT, ALB, ECS cluster/services/tasks, RDS, IAM, SNS, and alarms. Log groups are `/system-navigator/staging/{backend,worker,frontend,migration}`. Empty secret containers are `/system-navigator/staging/{database,cognito,stripe,email,ai/openai,ai/anthropic}`. The distinct RDS master secret is generated and managed by RDS. Production RDS, S3, Secrets, Cognito, ECS, ALB, logs, DNS, and provider configuration are never inputs to staging.

The default is a staging-only VPC. Setting `create_vpc=false` requires an existing VPC and at least two private and two public subnet IDs; supplying both modes fails validation. A dedicated VPC costs more because of NAT but provides clearer routing, quota, SG, and incident boundaries. A shared VPC is permitted only after network review.

## Workloads and least privilege

Backend, worker, frontend, and migration have separate task roles and task definitions; execution has a separate execution role. Frontend gets no S3 or secret task permission. Backend reads runtime secrets. Worker reads runtime secrets and, when enabled, the staging artifact bucket. Migration reads only the database secret. The GitHub staging role trusts only the repository's `staging` environment and has scoped ECS/pass-role permissions; no AdministratorAccess policy exists.

Backend runs `uvicorn app.main:app --host 0.0.0.0 --port 8000`, worker runs `python -m app.workers.runner`, frontend runs `node server.js`, and migration runs `alembic upgrade head`. Health checks cover `/health`, `/`, and `python -m app.workers.health`. Backend and frontend have separate target groups; backend/worker also register in a private service-discovery namespace.

## Providers, secrets, and HTTPS

Mock AI/payment/email default to true and must be shown clearly in the UI during testing. Cognito, Stripe, and SES default off. Cognito inputs are pool/client/issuer/domain; Stripe accepts secret ARNs, a publishable test key, and an HTTPS webhook endpoint; SES requires Sandbox, region, from address, and configuration set. Live Stripe mode and LocalAuth fail validation, and application startup refuses LocalAuth in staging/production.

Terraform never stores application secret values in code. Populate secret versions only through the separately approved secret-registration runbook, then record version ARNs without logging values. Staging SES sends only to verified Sandbox recipients. HTTPS requires an existing ACM ARN, domain, and Route53 zone; the ALB redirects HTTP to HTTPS when enabled. Terraform does not create Route53 records, ACM certificates, Cognito pools, Stripe webhooks, or SES identities in this phase.

## Data, migration, monitoring, and rollback

Staging RDS is PostgreSQL, private, encrypted, Single-AZ by default, deletion-protected, and backed up for seven days. The artifact bucket is unique, versioned, encrypted, public-blocked, TLS-only, lifecycle-managed, and has origin-minimized CORS. Migration and application database users are separated operationally: migration gets DDL for the approved task window; the app gets runtime DML only.

Monitoring defines ECS CPU/memory, ALB 5xx/unhealthy targets, RDS CPU/connections/storage, worker heartbeat, dead-letter growth, SNS notification, and a tag-filtered monthly budget. Before production-like testing, verify the application emits the two custom worker metrics.

Rollback selects previous immutable ECS task definitions, stops workers if schema compatibility is uncertain, and prefers a forward fix. A database restore creates a new instance from the verified snapshot; it never overwrites the old RDS. Preserve S3 versions, Secrets versions, logs, and audit evidence.

## Validation and approval boundaries

Allowed static workflow: `terraform fmt -recursive`, `terraform init -backend=false`, `terraform validate`, and local tests. Run production and staging roots separately. Before a plan, supply reviewed account ID, repositories/digests, unique bucket, production comparison names, OIDC provider ARN, network inputs, notification destination, and—if enabled—ACM/DNS/Cognito/Stripe/SES inputs.

Real AWS IDs, resource existence, quotas, IAM permissions, AZ/subnet capacity, ECR image presence, certificate/zone ownership, RDS engine availability, prices, alarm delivery, custom metric emission, and provider credentials remain unverified. Read-only AWS discovery requires human approval. Terraform plan, apply, secret registration, migration, ECS/ECR, DNS, Cognito, Stripe, and SES each remain separately approved actions.
