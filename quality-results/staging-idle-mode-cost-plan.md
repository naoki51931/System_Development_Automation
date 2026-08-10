# Staging IDLE mode cost and plan evidence

Collected 2026-08-10 for account `557604519341`, region `eu-west-2`, staging state `system-navigator/staging/terraform.tfstate`. Production root/state was not planned or modified. No apply, AWS mutation, snapshot, DB connection, migration, Secret value operation, EC2 stop or push occurred.

## Decision

`READY_FOR_STAGING_IDLE_MODE_REVIEW`

This means the code, review-only plan and restore runbook are ready for human review. It does **not** authorize apply. `RDS_IDLE_REMOVAL = BLOCKED`: no required manual snapshot/restore evidence exists, RDS deletion protection is currently true, and `idle_database_removal_approved=false` in the saved review plan.

## Gates

| Gate | Result |
|---|---|
| IDLE_MODE_DESIGN | PASS |
| RDS_DISABLED_IDLE | PASS in configuration/plan; apply BLOCKED |
| ALB_DISABLED_IDLE | PASS |
| INTERFACE_ENDPOINTS_DISABLED_IDLE | PASS (0; S3 Gateway retained) |
| RUNTIME_DISABLED_IDLE | PASS (services already 0; cluster/task definitions planned out) |
| PERSISTENT_DATA_PRESERVED | PASS (S3/ECR/state/Secret container retained; RDS requires snapshot before apply) |
| PRODUCTION_CHANGES_ZERO | PASS |
| RESTORE_WORKFLOW_DEFINED | PASS |
| RDS_SNAPSHOT_GATE | BLOCKED pending manual snapshot and restore test |
| TERRAFORM_VALIDATE | PASS, four roots |
| TESTS | PASS, 20 static Terraform tests |
| IDLE_PLAN_CREATED | PASS, ignored binary/text artifacts |
| COST_REDUCTION_ESTIMATE | ~$206–208/month; active ~$210 to idle ~$2–4 |

## Plan summary

Command used `terraform plan -var-file=terraform.tfvars -var='staging_mode=idle' -var='enable_runtime_services=false' -out=staging-idle.tfplan`. Saved artifacts are ignored and not committed.

| Action | Count |
|---|---:|
| add | 1 (`terraform_data.idle_apply_gate`) |
| change | 1 (task execution Secret policy drops the disappearing RDS-managed master Secret ARN) |
| replace | **0** |
| destroy | **35** |

Destroy groups: RDS 1; ALB/listener/rule/target groups/ALB SG and rules 9; Interface Endpoints 7 plus their SG 1; ECS cluster 1 and task definitions 4; Cloud Map namespace/services 3; infrastructure alarms 8; migration IAM inline policy 1. ECS runtime service destroys are zero because current service count is already zero.

The plan retains the staging VPC, six subnets, route tables and associations, Internet Gateway, task SG, DB SG and subnet group, S3 Gateway Endpoint, artifact bucket and protections, application Secret container, IAM roles and applicable policies, four 14-day log groups, remote state, and all prerequisite-state ECR/GitHub role/SNS/Budget resources. No `ai-platform-prod*`, Production VPC/RDS/ECS/ALB/NAT/S3/ECR or Production state address appears.

## Cost

Current fixed run rate is approximately $210/month: Interface Endpoints $127.75, RDS $54.9, ALB plus public IPv4 $26.62, and minor Secrets/ECR/S3/CloudWatch. Expected IDLE is approximately $2–4/month: ECR ~$0.14, retained application Secret ~$0.40, manual snapshot around $1.9 for 20 GB, and negligible current S3/CloudWatch plus small request/KMS variance. Expected reduction is $206–208/month (about 98%). Seven-day instead of 14-day log retention has effectively zero current saving, so 14 days remains.

Stopping work EC2 `i-0add395a2d89805b5` after commit/file/job checks would add about $38/month compute/public-IP saving; its EBS persists. No stop was performed.

## RDS and restore risk

The review plan includes RDS destroy, but direct apply is prohibited. Before a fresh approved plan: create/record an available manual snapshot, test restore, confirm services/tasks/connections/migration are idle, separately plan and approve deletion-protection false, run the guarded preflight, then obtain final plan approval. Restore uses `restore_db_from_snapshot=true` plus an ignored `db_snapshot_identifier`; empty creation and restore are mutually validated. The retained DB subnet group/SG and identifier are reused. After RDS is available, create the application DB user, update `/system-navigator/staging/database` outside Terraform, confirm PITR and schema/Alembic revision, migrate separately, enable services, then smoke test.

Risk is high for RDS data/recovery, medium for activation time and ALB DNS change, and low for persistent foundation cost. Production impact is zero by root/state isolation.

## Network decision

IDLE uses neither NAT nor paid Interface Endpoints and retains the free S3 Gateway Endpoint. For ACTIVE private tasks, one NAT (~$36.50/month plus data/EIP) is recommended over 14 endpoint-AZ attachments (~$127.75/month), subject to a separate security/egress plan. Public-IP Fargate is cheapest for very short synthetic tests but is not implemented and requires security approval.

## Verification

- Four roots (`bootstrap`, `environment`, `environment/staging`, `environment/staging-prerequisites`): `fmt -recursive -check`, `init -backend=false`, `validate` PASS.
- ACTIVE check plan: zero resource changes with runtime services disabled; expected outputs are RDS 1, ALB 1, Interface Endpoints 7, services 0.
- IDLE plan: outputs RDS 0, ALB 0, Interface Endpoints 0, services 0; zero replacement.
- Docker pytest: 20 passed; one harmless cache warning because the repository was mounted read-only.
