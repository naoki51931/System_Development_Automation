# Staging Idle Mode drift investigation

- Investigation time: 2026-08-12 UTC
- Git HEAD: `572751fec5f8c7f3151e8737805c91f65476da2f`
- AWS account: `557604519341`
- Region: `eu-west-2`
- Terraform state key: `system-navigator/staging/terraform.tfstate`
- State lineage / serial: `47717f58-dbeb-a083-7715-e3bc91e652c6` / `12`
- State object last modified: `2026-08-11T07:25:48Z`
- Old plan: `environment/staging/staging-final-idle.tfplan`
- Old plan SHA-256: `b2c8ab750e3f939a6023d89df921bcb7fd78c5bd4891de1d1a260520f4f3ee1a`
- Investigation mode: read-only; no apply, state mutation, or AWS mutation was performed.

## Finding

The old Idle plan has effectively already been applied by another invocation. Terraform state and AWS both represent the Idle resource set. The current local `terraform.tfvars`, however, resolves to `staging_mode = active`, so the requested drift-review plan proposes rebuilding the active resources. It must not be applied as an Idle reconciliation.

Evidence linking the deletion to a Terraform execution:

- CloudTrail records the RDS, ALB, seven Interface Endpoints, ECS cluster/task definitions, Cloud Map namespace, and eight staging alarms being deleted at `2026-08-11T07:18:51Z`–`07:18:52Z`.
- All inspected deletion calls used `arn:aws:sts::557604519341:assumed-role/instanceRoleTerraform/i-0add395a2d89805b5` from `3.10.174.9`.
- RDS reported shutdown at `07:18:56Z` and deletion completion at `07:25:20Z`.
- The remote Terraform state object was updated at `07:25:48Z` and now has Idle outputs (`rds=0`, `alb=0`, `interface_endpoints=0`, `runtime_services=0`).
- The state contains `terraform_data.idle_apply_gate[0]`, which the old plan created, while all 35 old-plan destroy addresses are absent.

## RDS

- Terraform address: `module.database.aws_db_instance.main[0]`
- Terraform state: absent (`terraform state show` returned `No instance found for the given address`).
- Current state identifier / deletion protection / instance class: not applicable because the instance is no longer in state. For historical context, the old plan's captured pre-delete state was identifier `system-navigator-staging-db`, deletion protection `false`, and class `db.t4g.small`. The current active-mode create proposal would use deletion protection `true` and class `db.t4g.small`.
- AWS: `DBInstanceNotFound`.
- Classification: both missing.
- RDS event: shutdown `2026-08-11T07:18:56.952Z`; deleted `2026-08-11T07:25:20.609Z`.
- CloudTrail: `DeleteDBInstance` at `2026-08-11T07:18:52Z`, Terraform instance role above, `skipFinalSnapshot=false`, final snapshot identifier `system-navigator-staging-db-final`, automated backup deletion requested.
- Manual snapshot `system-navigator-staging-pre-idle-20260811-013548`: available, encrypted, source `system-navigator-staging-db`.

## Idle resource inventory

| Resource group | Terraform state | AWS | Classification |
| --- | --- | --- | --- |
| RDS instance | missing | missing | both missing |
| Staging ALB/listener/target groups | missing | missing | both missing |
| Seven Interface Endpoints | missing | missing | both missing |
| Endpoint security group | missing | missing | both missing |
| ECS cluster/services | missing | missing | both missing; services/tasks zero |
| Staging task definitions | missing | no ACTIVE or INACTIVE definitions returned | both missing |
| Cloud Map namespace/services | missing | missing | both missing |
| Idle-target CloudWatch alarms | missing | missing | both missing |

Only the production ALB and production target group were returned account-wide. The staging VPC contains exactly one endpoint: the S3 Gateway endpoint `vpce-0d82ede055c29c866`, state `available`.

## Preserved resources

- VPC `vpc-0b5ce4ab333cc5b7c`: available.
- Subnets: six available (two public, two private, two database).
- Route tables: public, private, and main route tables exist.
- Internet Gateway `igw-058a4f32f97d56fbf`: attached/available.
- DB subnet group `system-navigator-staging-db`: Complete, two subnets.
- DB security group `sg-0d809b8aac1d6bbac`: exists.
- S3 Gateway endpoint `vpce-0d82ede055c29c866`: available.
- Artifact S3 `system-navigator-staging-artifacts-557604519341`: exists.
- ECR: `system-navigator-staging-app` and `system-navigator-staging-frontend` exist.
- IAM deploy role `system-navigator-staging-github-deploy`: exists. Runtime/task IAM retained in Terraform state.
- SNS `system-navigator-staging-alerts`: exists.
- Budget `system-navigator-staging-monthly`: exists, USD 150 limit.
- Secret container `/system-navigator/staging/database`: exists and is not scheduled for deletion. No secret value was read.
- CloudWatch Log Groups: backend, frontend, migration, and worker exist.
- Terraform state object exists and is KMS encrypted.
- Manual RDS snapshot exists, is available and encrypted.

## Review plans

Old saved plan inputs/actions:

- `staging_mode=idle`
- add 1, change 1, replace 0, destroy 35
- Validity: **INVALID** for current state. Its destroy targets are already absent and its one create target is already present in state. It represents the transition that already occurred and must not be applied again.

New review-only plan `environment/staging/staging-current-drift-review.tfplan`:

- Local resolved input: `staging_mode=active`, `enable_runtime_services=false`.
- add 35, change 1, replace 0, destroy 1.
- The 35 creates are the inverse of the completed Idle transition: RDS, ECS cluster and four task definitions, ALB set, Cloud Map, monitoring alarms, endpoint SG, and seven Interface Endpoints.
- The one update is `module.ecs.aws_iam_role_policy.execution_secrets`.
- The one destroy is `terraform_data.idle_apply_gate[0]`.
- This is configuration drift toward Active Mode, not evidence of AWS resources missing from an Idle state. Apply is prohibited.

## Cost and production

RDS, ALB/Public IPv4, and all seven Interface Endpoints are absent. Using the reviewed estimate, approximately USD 206–208/month of fixed cost has already been removed, leaving an estimated Idle cost of approximately USD 2–4/month. Cost Explorer lag was not used as primary evidence.

Production remained unchanged in this investigation:

- RDS `ai-platform-prod-postgres`: available, deletion protection enabled.
- ECS `ai-platform-prod`: ACTIVE, one active service, one running task, zero pending.
- ALB `ai-platform-prod`: active.
- NAT `nat-041c10f70dc672ab4`: available.
- VPC `vpc-0da4eaf0768153c5c`: available.
- ECR `ai-platform-prod`: exists.

## Gates

- `OLD_IDLE_PLAN_VALIDITY=INVALID`
- `RDS_STATE_STATUS=MISSING`
- `RDS_AWS_STATUS=MISSING`
- `ALB_STATUS=REMOVED`
- `INTERFACE_ENDPOINT_STATUS=REMOVED_0_REMAINING`
- `ECS_STATUS=REMOVED_SERVICES_0_TASKS_0`
- `CLOUD_MAP_STATUS=REMOVED`
- `MONITORING_STATUS=IDLE_TARGET_ALARMS_REMOVED_LOG_GROUPS_PRESERVED`
- `PERSISTENT_RESOURCES_STATUS=PASS`
- `CURRENT_TERRAFORM_DRIFT=ACTIVE_CONFIG_PROPOSES_35_ADD_1_CHANGE_1_DESTROY`
- `PRODUCTION_CHANGES_ZERO=PASS`

Final decision: **STAGING_IDLE_MODE_ALREADY_EFFECTIVE**.

Human approval is required before changing local configuration to make Idle Mode the current declared configuration and generating a clean reconciliation plan. The old saved plan and the active-mode drift-review plan must not be applied.
