# Staging IDLE/ACTIVE mode

## Contract

`environment/staging` has two cost modes. `staging_mode = "idle"` retains the separate remote state, VPC CIDR/subnets/routes/Internet Gateway, task security group, DB subnet group and DB security group, S3 Gateway Endpoint, artifact S3 bucket, application Secret container, IAM roles/policies that remain applicable, and four 14-day CloudWatch log groups. ECR, the GitHub deploy role, SNS and Budget remain in the independent `staging-prerequisites` state.

IDLE excludes the RDS instance, seven Interface Endpoints, ALB/listener/target groups/public IPs, ECS cluster/task definitions/services, Cloud Map namespace/services, ALB/RDS/runtime alarms, and ALB security rules. `terraform destroy` is never the mode transition.

`staging_mode = "active"` creates that runtime infrastructure. `enable_runtime_services` is a second, later gate: ACTIVE first creates connectivity, DB, ALB and definitions with services still zero; services are enabled only after database restore/create, Secret registration, backup checks and migration.

The explicit flags remain visible because they express materially different choices:

```hcl
staging_mode                 = "idle" # or active
allow_staging_reactivation   = false  # true only for a separately reviewed IDLE-to-ACTIVE plan
allow_database_deletion      = false  # true only for separately reviewed protection/removal phases
enable_interface_endpoints  = true   # effective only in active
enable_s3_gateway_endpoint  = true   # retained in both modes
enable_nat_gateway          = false
enable_runtime_services     = false
restore_db_from_snapshot    = false
db_snapshot_identifier      = ""     # ignored file/CLI only
```

Do not commit real snapshot IDs, tfvars, backend files, plans or state.

Changing an ignored local tfvars file from `staging_mode="idle"` to `"active"` recreates the costly RDS, ALB/Public IPv4, seven Interface Endpoints, ECS/task definitions, Cloud Map and alarms. Terraform therefore rejects ACTIVE unless `allow_staging_reactivation=true` is also supplied. The approval flag authorizes planning only; a reviewed saved plan and a separate apply approval are still mandatory.

## Network choice for ACTIVE

| Choice | Fixed monthly estimate | Security and operation | Required service access | Decision |
|---|---:|---|---|---|
| 7 Interface Endpoints × 2 AZ | ~$127.75 | Strong private path; many resources and high fixed cost | ECR API/DKR, Logs, Monitoring, Secrets, STS, KMS; S3 Gateway | Not recommended for intermittent staging |
| 1 NAT Gateway | ~$36.50 + EIP/data | Tasks remain private; simple, broad egress needs SG/NACL controls | Covers all listed APIs and image pulls; S3 can stay on free Gateway Endpoint | **Recommended ACTIVE default** when activation lasts more than a few hours or private tasks are required |
| Selected endpoints + connectivity | ~$18.25 per two-AZ endpoint-month | Least privilege possible, but combinations are easy to break | ECR pull needs ECR API + DKR + S3; logging needs Logs; secrets needs Secrets | Use only after traffic/dependency proof; seven endpoints cost more than NAT |
| Fargate public IP, no NAT/interfaces | $3.65/task public-IP-month prorated, no gateway fixed fee | Cheapest intermittent path, but tasks get public addresses; SG must deny ingress and egress should be constrained | Direct ECR/Logs/Secrets/STS/KMS/S3 access | Cost winner for short synthetic staging, but approve only after security review |

The recommended baseline is IDLE with neither NAT nor Interface Endpoints. For ACTIVE, use one NAT Gateway for the safest low-operational-cost private-task configuration. For very short-lived, non-sensitive synthetic testing, `assign_public_ip=true` can be a separately reviewed future option; it is not implemented by this change. EIP quota must be checked before NAT creation. Current code keeps NAT false and the known-working endpoints true until that architecture change receives its own plan.

## RDS removal gate

RDS stop/start is useful only for an idle window below seven days; storage continues billing and AWS automatically restarts it. Continuous `db.t4g.small` costs about $54.9/month. Long idle uses manual snapshot → remove instance → restore on activation. No automated snapshot is sufficient for this gate.

Before an approved IDLE removal:

1. Confirm ECS services = 0 and no running migration/one-off tasks.
2. Confirm application owners have ended writes and review CloudWatch `DatabaseConnections`; DB login is not part of the Terraform gate.
3. Create a manual snapshot in a separately approved operation, record its ARN/identifier, source DB, engine/version, KMS key, timestamp and owner, and wait for `available`.
4. Test restore into a disposable staging-only identifier in a separately approved exercise; verify PostgreSQL engine, schema/Alembic revision, synthetic data and application login, then remove that test only after approval.
5. Use a separate ACTIVE-mode plan with `allow_database_deletion=true`, `idle_database_removal_approved=true`, and the available manual snapshot input to set only RDS `deletion_protection=false`. Review and apply only that saved plan after separate approval. A later fresh IDLE plan must again set both approval flags and the snapshot input. Routine ACTIVE and IDLE inputs leave the gate false.
6. Set the two approval environment values required by `scripts/staging_idle_apply.sh`. The script checks the manual snapshot, deletion protection, ECS services and tasks, creates a new approved plan, then deliberately stops before apply.
7. A human reviews that fresh plan and separately authorizes apply. Never apply `staging-idle.tfplan`; it has `idle_database_removal_approved=false`.

`prevent_destroy` remains on the artifact bucket. RDS intentionally no longer has Terraform `prevent_destroy`, because count-based IDLE removal must be representable, but deletion protection, manual snapshot lookup, explicit approval inputs, the wrapper checks, saved-plan review and human apply approval form the removal gate. `RDS_IDLE_REMOVAL = BLOCKED` until all are satisfied.

## IDLE to ACTIVE restore

1. Select the recorded manual snapshot. Set `staging_mode="active"`, `allow_staging_reactivation=true`, `restore_db_from_snapshot=true`, `db_snapshot_identifier=<ignored input>`, `enable_runtime_services=false`, and choose connectivity. `restore_db_from_snapshot` and the identifier are mutually required by Terraform validation. The reactivation approval must return to false in IDLE.
2. Plan Phase 1. It creates Interface connectivity/NAT as approved, ALB, RDS restored with the same identifier/subnet group/security group, ECS cluster/task definitions and Cloud Map. Review zero Production addresses and apply only after approval.
3. Wait for RDS `available`. Create/verify the application DB user through the separately approved administrative procedure. Update `/system-navigator/staging/database` outside Terraform with the new endpoint/database/user/password. Terraform never manages Secret values.
4. Confirm automated backup/PITR and perform the documented backup preflight. Confirm the restored schema/Alembic revision before selecting migration SQL.
5. Run the migration task only after separate DB/migration approval; require exit 0 and Alembic head.
6. Plan `enable_runtime_services=true`, review three services, then apply after approval.
7. Verify backend `/health`, frontend `/login`, ALB targets, worker health, logs, alarms and synthetic smoke tests. Never use Production data or credentials.

For a new empty database, keep both restore inputs false/empty. Snapshot identifier input must never be fixed in Git. Reusing `system-navigator-staging-db`, the retained DB subnet group and DB SG stabilizes application configuration; the RDS endpoint may still change, so Secret update is mandatory.

## Work EC2 shutdown runbook

`i-0add395a2d89805b5` is outside staging Terraform. Stopping it can save about $34.46/month compute plus up to $3.65/month public IPv4; its 30-GB EBS volume (~$2.78/month) remains.

Before a separately approved stop: commit all intended code locally, verify `git status` and required untracked files/backups, confirm no AWS/Terraform command or long-running local job remains, record restart owner and access method, and expect the ephemeral public IP to change. Then an authorized human may run `aws ec2 stop-instances --instance-ids i-0add395a2d89805b5 --region eu-west-2`. This command was not run during this work.

## Cost floor

Expected IDLE recurring cost is approximately $2–4/month: ECR ~$0.14, application Secret ~$0.40 (plus any other intentionally retained containers), S3/CloudWatch near zero at current volume, snapshot storage roughly $1.9 for 20 GB, and small KMS/request variance. Route53, ALB, RDS instance/storage, Interface Endpoints and Fargate are absent. Changing log retention from 14 to 7 days saves effectively $0 at the current zero/small log volume, so 14 days is retained for evidence.
