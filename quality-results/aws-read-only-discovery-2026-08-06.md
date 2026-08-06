# AWS read-only discovery — 2026-08-06

## Scope and identity

This evidence was collected with AWS CLI read-only `get`, `list`, `describe`, and `head` operations. No Terraform plan/apply/import, AWS mutation, Secret value read, RDS connection, object write, provider connection, or push occurred.

- Account: `557604519341`; Region: `eu-west-2`.
- Caller: `arn:aws:sts::557604519341:assumed-role/instanceRoleTerraform/i-0add395a2d89805b5` via EC2 instance profile `instanceRoleTerraform`.
- Caller managed policies: `CloudWatchAgentServerPolicy`, `AmazonSSMManagedInstanceCore`, and `AdministratorAccess`; no inline policy or permission boundary. Commands remained read-only despite administrative capability.
- Caller trust principal is EC2. Maximum role session is 3600 seconds.

## Terraform state

- Bucket `ai-platform-terraform-state-557604519341` exists in `eu-west-2`, has versioning, all four public-access blocks, and default SSE-KMS.
- Production object `cloud-a/prod/terraform.tfstate` exists and was last modified 2026-08-01 14:20 UTC. Its content was not read.
- Staging object `system-navigator/staging/terraform.tfstate` returned 404, which is expected before first approved apply.
- KMS key `arn:aws:kms:eu-west-2:557604519341:key/7aba3a9a-cda4-498b-99e5-e8e3e00bf64c` is Enabled, customer-managed, symmetric single-Region, encrypt/decrypt, with 365-day rotation. No alias exists. Key policy was not retrieved.

## Production inventory

### Network and security

- VPC `vpc-0da4eaf0768153c5c`, `10.20.0.0/16`, named `ai-platform-prod-vpc`.
- Public: `subnet-039582b5311a27894` (`10.20.0.0/24`, 2a, 249 free) and `subnet-067800de3200aa6ca` (`10.20.1.0/24`, 2b, 250 free), default route through `igw-05ebba654d3293cf7`.
- Private: `subnet-0b224e86387598728` (`10.20.10.0/24`, 2a, 250 free) and `subnet-0b0528c6af4fecff9` (`10.20.11.0/24`, 2b, 251 free), default route through `nat-041c10f70dc672ab4`.
- Database: `subnet-0070a1013b746a51c` (`10.20.20.0/24`, 2a, 250 free) and `subnet-0ebc0123e8365ea79` (`10.20.21.0/24`, 2b, 250 free), with local-only main route table.
- ALB SG `sg-02a3fdf120217dca7` exposes TCP/80 to `0.0.0.0/0`; app SG `sg-0e2a45d414c8df95c` allows 8000 only from ALB SG; DB SG `sg-0cf44bce2c1b60b2e` allows 5432 only from app SG. No production SSH ingress exists.
- No VPC peering, VPN connection, or Transit Gateway was found. Candidate staging CIDR `10.30.0.0/16` does not overlap discovered VPCs.

### ECS, ALB, and ECR

- ECS cluster/service `ai-platform-prod` is ACTIVE: desired/running/pending `1/1/0`, Fargate, rollout COMPLETED, private subnets, no public IP.
- Task definition `ai-platform-prod:4`: 512 CPU, 1024 MiB, image `ai-platform-prod:v4`, no command override, no ECS Secret reference, `/health` container check.
- ALB `ai-platform-prod` is internet-facing and active at `ai-platform-prod-1767582825.eu-west-2.elb.amazonaws.com`. It has HTTP/80 only, idle timeout 60, deletion protection false, and invalid-header dropping false. Target `10.20.10.219:8000` is healthy.
- ECR has only `557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod`, immutable tags, scan-on-push, AES256, no lifecycle policy. Tags are `v1`–`v4`; `v4` digest is `sha256:3f447ba97a9db2722446e5913ce0a06bc08b833bc8092f6f7a26eb25c5613d57`.
- No `57109fa` tag/digest and no staging backend/worker/frontend repositories exist. This blocks the image inputs.

### RDS and S3

- RDS `ai-platform-prod-postgres`: available PostgreSQL 18.3, `db.t4g.medium`, 50 GiB gp2, encrypted, Multi-AZ, private, 14-day retention, deletion protection. Endpoint is `ai-platform-prod-postgres.ctki48ayuz30.eu-west-2.rds.amazonaws.com`; no connection was attempted.
- Latest PITR time: 2026-08-06 04:52 UTC. Latest automated snapshot: 2026-08-05 23:10 UTC. No manual snapshot exists. PostgreSQL log export is disabled.
- Artifact bucket `ai-platform-artifacts-557604519341`: eu-west-2, AES256, versioning and public block enabled; no bucket policy, lifecycle, or CORS.
- Candidate `system-navigator-staging-artifacts-557604519341` and DB identifier `system-navigator-staging-db` do not collide. PostgreSQL 17.10, `db.t4g.small`, and gp3 are orderable in 2a/2b/2c.

## Identity and integrations

- Only Secret is `ai-platform-prod/database`; rotation is not enabled. All six planned `/system-navigator/staging/*` containers are missing. Secret values were never requested.
- GitHub OIDC exists at `arn:aws:iam::557604519341:oidc-provider/token.actions.githubusercontent.com`, audience `sts.amazonaws.com`. Existing role `ai-platform-prod-github-deploy` trusts `repo:naoki51931/System_Development_Automation:*`, with no branch/environment restriction, attached policy, inline policy, or boundary. A staging-only role is missing.
- Public Route53 zone `true-camera-test.com` is `Z05220783EQSOCLA4YS4T`; `staging.true-camera-test.com` does not exist. No ACM certificate exists in eu-west-2.
- No Cognito User Pool exists. Cognito is disabled in proposed staging inputs, so it is not required for the initial mock-auth phase.
- SES is in Sandbox (`ProductionAccessEnabled=false`) with sending enabled, one successfully verified email identity, one failed domain identity, suppression for bounce/complaint, and configuration set `my-first-configuration-set`. The email identity value was deliberately not collected.

## Monitoring, budgets, and quotas

- CloudWatch has `/ecs/ai-platform-prod` with 30-day retention. No alarm exists. No staging log name collision exists.
- No SNS topic/subscription exists. Budget API returned no budget collection; there is no confirmed existing staging budget or notification target.
- Discovered quotas/current inventory: VPC 2/5; NAT 1 (quota 5 per AZ); EIP 4/5; ALB 1/50; target groups 1/3000; RDS instances 1/40; DB subnet groups quota 50; Secrets 1/500000; Cognito pools 0/1000; Fargate On-Demand quota 8 vCPU. Production uses 0.5 Fargate vCPU and proposed staging uses 1.5 vCPU, leaving nominal headroom.
- S3 bucket quota and ECS services-per-cluster quota were not returned by Service Quotas; current counts are S3 buckets 2 and ECS services 1. Exact current Fargate usage metric and quota availability at plan time remain unverified. Therefore `QUOTAS_CONFIRMED` is BLOCKED rather than PASS.

## Staging candidates and blockers

| Input | Candidate | Status |
|---|---|---|
| `aws_account_id` / `aws_region` | `557604519341` / `eu-west-2` | EXISTS |
| `state_bucket_name` | `ai-platform-terraform-state-557604519341` | EXISTS |
| `state_kms_key_arn` | `arn:aws:kms:eu-west-2:557604519341:key/7aba3a9a-cda4-498b-99e5-e8e3e00bf64c` | EXISTS |
| `staging_backend_key` | `system-navigator/staging/terraform.tfstate` | MISSING object; intended new key |
| `github_oidc_provider_arn` | `arn:aws:iam::557604519341:oidc-provider/token.actions.githubusercontent.com` | EXISTS |
| backend/worker/frontend ECR URL | none | MISSING |
| `container_image_tag` / digest | intended `57109fa` / none | MISSING |
| `artifact_bucket_name` | `system-navigator-staging-artifacts-557604519341` | REQUIRES_APPROVAL; name free |
| `production_artifact_bucket_name` | `ai-platform-artifacts-557604519341` | EXISTS |
| `staging_db_identifier` | `system-navigator-staging-db` | REQUIRES_APPROVAL; name free |
| `production_db_identifier` | `ai-platform-prod-postgres` | EXISTS |
| alarm notification target | none collected | MISSING |
| `monthly_budget_amount` | proposed 100 USD | REQUIRES_APPROVAL |
| `route53_zone_id` | `Z05220783EQSOCLA4YS4T` | EXISTS |
| `domain_name` | `staging.true-camera-test.com` | REQUIRES_APPROVAL; record free |
| `acm_certificate_arn` | none | MISSING |
| Cognito pool/client/issuer | none | MISSING; NOT_REQUIRED while disabled |
| `ses_region` | `eu-west-2` | EXISTS |
| `ses_from_address` | deliberately not collected | UNKNOWN; NOT_REQUIRED while disabled |
| `ses_configuration_set` | `my-first-configuration-set` | EXISTS |
| Network | dedicated `10.30.0.0/16` | REQUIRES_APPROVAL; no discovered overlap |

Additional AWS resources required by the current Terraform design are staging VPC/subnets/routes/NAT/IGW, ECS/ALB/service discovery/tasks/IAM, RDS, S3, six Secret containers, logs/alarms/SNS/Budget, and optionally ACM/Route53/Cognito/SES resources after separate approval.

## Plan-review gates

`AWS_ACCOUNT_CONFIRMED`, `REGION_CONFIRMED`, `STATE_BACKEND_CONFIRMED`, `STATE_KMS_CONFIRMED`, `PRODUCTION_RESOURCE_INVENTORY_CONFIRMED`, `STAGING_NAME_COLLISION_CHECKED`, `OIDC_CONFIRMED`, `NETWORK_INPUTS_CONFIRMED`, `RDS_INPUTS_CONFIRMED`, and `S3_INPUTS_CONFIRMED` are PASS.

`ECR_REPOSITORY_CONFIRMED` and `IMAGE_TAG_OR_DIGEST_CONFIRMED` are FAIL. `IAM_BOUNDARIES_CONFIRMED`, `ROUTE53_ACM_CONFIRMED`, `MONITORING_INPUTS_CONFIRMED`, and `QUOTAS_CONFIRMED` are BLOCKED. Cognito and SES inputs are NOT_REQUIRED while their enable flags remain false.

Final decision: **NOT_READY_FOR_TERRAFORM_PLAN_REVIEW**. Terraform plan was not run.
