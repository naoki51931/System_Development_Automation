# Staging pre-plan remediation — 2026-08-06

## Decision and boundaries

The repository is **READY_FOR_PRE_PLAN_RESOURCE_APPROVAL**. This means humans can review the narrowly scoped prerequisite creation and input decisions below. It does not authorize ECR creation/push, IAM/ACM/DNS/SNS/Budget/Secret creation, Terraform plan/apply, RDS access, migration, or deployment.

## ECR and image design

The selected design uses two repositories. `system-navigator-staging-app` serves backend, worker, and migration because they use one Dockerfile, filesystem, dependency set, and reviewed commit; ECS commands and roles remain separate. `system-navigator-staging-frontend` serves the standalone Next.js runtime. Three repositories would duplicate builds, scans, storage, digest tracking, and rollback without improving runtime privilege separation.

Both repositories are immutable, scan-on-push, AES256 encrypted, `force_delete=false`, expire untagged images after seven days, and retain 20 reviewed tagged generations. A separate `environment/staging-prerequisites` root owns only these repositories in `system-navigator/staging/prerequisites.tfstate`. This resolves repository-before-push-before-digest ordering without permanent `-target`. The main staging state consumes full digest URIs and does not own ECR.

### Local images and tests

- Application: `system-navigator-staging-app:57109fa`, local ID `sha256:e069abf0d9a457b6689c9b3d69532dbd6ca2b9c4bee3a8e96c520cdf01b73fdb`, 69,335,027 bytes, linux/amd64, user `app`, uvicorn default, `/health` healthcheck.
- Frontend: `system-navigator-staging-frontend:57109fa`, local ID `sha256:5c2eeeee402293fa783c9a6dd67b6f03dce00b3651ef73d314f773d3371e82dc`, 61,213,044 bytes, linux/amd64, user `nextjs`, `docker-entrypoint.sh`, `node server.js`, `/login` healthcheck.
- Both have OCI revision `57109fa`. Local IDs are not ECR manifest digests and cannot be placed in Terraform.
- Backend `/health` and `/docs` returned 200 under staging settings; it selected `CognitoAuthProviderStub`. Worker used the same image with `python -m app.workers.runner`, connected only to local Compose PostgreSQL, returned healthy, and stopped gracefully. Frontend `/` and `/login` returned 200, ran standalone/non-root, hid LocalAuth, and showed `Mock Provider使用中（AI / 決済 / メール）`.

Security results: Bandit 0, pip-audit 0 known vulnerabilities, npm runtime audit critical/high/moderate/low all 0, tracked-file secret scan 0, and no credential/private-key file in runtime images. Trivy is unavailable locally; ECR scan-on-push must show zero critical/high findings before promotion.

Final local gates: all four Terraform roots validate; recursive fmt passes; Terraform safety tests are 15 passed/1 provider-schema skip; backend is 137 passed with 83.09% overall and 90.86% critical-service coverage; frontend is 34 passed; build and OpenAPI drift checks pass; all four Compose services are healthy and the reference seed succeeds twice.

### Planned push — not executed

After separately approved prerequisites apply and push approval:

```bash
aws ecr get-login-password --region eu-west-2 | docker login --username AWS --password-stdin 557604519341.dkr.ecr.eu-west-2.amazonaws.com
docker tag system-navigator-backend:57109fa 557604519341.dkr.ecr.eu-west-2.amazonaws.com/system-navigator-staging-app:57109fa
docker tag system-navigator-frontend:57109fa 557604519341.dkr.ecr.eu-west-2.amazonaws.com/system-navigator-staging-frontend:57109fa
docker push 557604519341.dkr.ecr.eu-west-2.amazonaws.com/system-navigator-staging-app:57109fa
docker push 557604519341.dkr.ecr.eu-west-2.amazonaws.com/system-navigator-staging-frontend:57109fa
aws ecr describe-images --repository-name system-navigator-staging-app --image-ids imageTag=57109fa --region eu-west-2
aws ecr describe-images --repository-name system-navigator-staging-frontend --image-ids imageTag=57109fa --region eu-west-2
```

The returned registry digests form `backend_image_uri`, `worker_image_uri`, and `frontend_image_uri` as `repository@sha256:...`. Backend and worker equality plus account/region ownership are validated. Rollback selects a prior immutable digest; repositories are retained unless empty, unused, and separately approved for deletion.

## Deploy role and HTTPS

`system-navigator-staging-github-deploy` trusts audience `sts.amazonaws.com` and subject exactly `repo:naoki51931/System_Development_Automation:environment:staging`. GitHub Environment protection must allow only `agent/final-quality-gate` during this gate or approved `main`; environment and branch-ref subjects cannot both occupy one GitHub OIDC `sub`.

Permissions cover login/push only to the two staging ECR repositories, staging ECS registration/describe/run/update, `iam:PassRole` only for staging roles, read-only staging logs, the staging state prefix/lock object, and its KMS key. There is no AdministratorAccess or wildcard repository trust. Broad infrastructure creation remains a separately approved operator responsibility. Rollback disables the workflow/environment first, then removes policy and role after active sessions are excluded.

HTTPS option A is selected from the first main apply. HTTP-only is unsuitable for cookies, CSRF, future Cognito/Stripe callbacks, and production-equivalent testing. Terraform can request `staging.true-camera-test.com`, create only DNS validation records in `Z05220783EQSOCLA4YS4T`, validate ACM, configure HTTPS/HTTP redirect, and create the ALB alias. Alternatively a pre-created ARN can be supplied, but exactly one certificate source is allowed. Rollback removes alias/listener dependencies before certificate deletion.

## SNS, Budget, and Secrets

Monitoring creates `system-navigator-staging-alerts`, an optional email subscription from ignored tfvars, and an account-limited AWS Budgets publish policy. The recipient must confirm the SNS email. Budget amount and AWS billing currency require human approval; 100 or 150 GBP are discussion values only. Alerts are actual 50/80/100% and forecasted 100%.

Initially only `/system-navigator/staging/database` is created. Cognito, Stripe, email, OpenAI, and Anthropic containers are conditional on enabling those real providers. Terraform manages no Secret version/value. RDS has a distinct managed master Secret. Secret rollback uses the 30-day recovery window and never force-deletes populated data.

## Network and quota decision

The dedicated `10.30.0.0/16` VPC spans eu-west-2a/2b with two public `/24`, two private application `/24`, and two isolated database `/24` subnets. No discovered network overlaps it.

- One NAT is simple but consumes the fifth of five EIPs, is one-AZ, costs continuously, and permits generic egress.
- Two NATs improve AZ availability but exceed the EIP quota and double NAT cost.
- Sharing production NAT expands routing and incident blast radius and is rejected.
- No NAT plus endpoints removes public task egress/EIP use but adds endpoint ENI/hourly costs and supports only enumerated services.

The selected initial design is no NAT plus interface endpoints for ECR API/DKR, Logs, Monitoring, Secrets Manager, STS, and KMS, with an S3 gateway endpoint. Mock providers need no generic internet egress. Endpoint versus NAT cost still requires approval; security and EIP isolation drive the default.

Quota supplementation found Fargate actual maximum 0.5/8 vCPU, EIP 4/5, one NAT in eu-west-2a, two S3 buckets, and one active ECS service. S3 bucket-count quota and ECS services-per-cluster were not exposed by the queried APIs, so remain UNKNOWN despite low current counts.

## Input classification

| Input | Classification |
|---|---|
| account, region, state bucket/KMS/key, OIDC | CONFIRMED |
| two ECR repositories | REQUIRES_RESOURCE_CREATION |
| application/frontend registry digest URIs | REQUIRES_RESOURCE_CREATION after approved push |
| artifact bucket, staging DB, ACM ARN, alias | GENERATED_BY_TERRAFORM in main state |
| production artifact bucket/DB identifier | CONFIRMED |
| alarm email | REQUIRES_HUMAN_INPUT; ignored tfvars only |
| Budget amount and billing currency | REQUIRES_HUMAN_INPUT |
| zone `Z05220783EQSOCLA4YS4T`, domain `staging.true-camera-test.com` | CONFIRMED |
| Cognito pool/client, SES from address | NOT_REQUIRED_INITIAL_STAGE |

## Staged execution and stop conditions

1. Separately approve plan/apply of `environment/staging-prerequisites` for two ECR repositories only.
2. Approve image push, require ECR scan critical/high zero, capture registry digests, and populate ignored main tfvars.
3. Review one complete main staging plan for IAM, endpoint-only VPC, S3, database Secret container, SNS/Budget, ACM/DNS, RDS, ECS/ALB/tasks/services. Main state is applied as a graph without routine `-target`.
4. After approved apply and snapshot controls, run migration task only; exit 0 and Alembic head are mandatory before service stabilization.
5. Run HTTPS, LocalAuth rejection, Mock banner, tenant, worker, S3, alarm, Budget, and rollback smoke tests.

The prerequisites state is a narrow bootstrap boundary; further state fragmentation is rejected because it increases cross-state coupling. Stop before main plan review if repository URLs/digests are absent, backend/worker digests differ, scans contain critical/high findings, Budget/alert inputs or GitHub Environment protection are unresolved, the CIDR gains a collision, endpoint/NAT policy changes without approval, or production addresses/state appear in a diff.

No AWS creation, ECR push, Terraform plan/apply, DNS change, Secret value operation, RDS connection, migration, ECS update, or GitHub push occurred.
