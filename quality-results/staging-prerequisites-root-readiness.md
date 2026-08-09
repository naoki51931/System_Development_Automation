# Staging prerequisites root readiness

`environment/staging-prerequisites` is ready for a separately approved Terraform plan. Its backend key is `system-navigator/staging/prerequisites.tfstate`, distinct from production `cloud-a/prod/terraform.tfstate` and main staging `system-navigator/staging/terraform.tfstate`.

The root owns exactly the two immutable, scan-on-push AES256 ECR repositories and lifecycle policies; `system-navigator-staging-github-deploy` with GitHub Environment `staging` trust; the `staging.true-camera-test.com` ACM certificate and Route53 validation records; `system-navigator-staging-alerts` plus its email subscription; and `system-navigator-staging-monthly` at 100 GBP with four direct email notifications. The SNS subscription remains `PendingConfirmation` until a human confirms it.

CloudWatch alarms are main-staging resources and publish to the prerequisite SNS topic. AWS Budget notifications go directly to `info@nagi-neco.com`, not through SNS. Main staging receives ECR URLs/digests, deploy-role ARN, certificate ARN and SNS ARN as explicit ignored inputs. Prerequisites never reads main state.

VPC, subnets, endpoints, artifact S3, Secrets, RDS, ECS, ALB, services, task definitions, final Route53 ALB alias and CloudWatch alarms are excluded. No Terraform plan/apply, AWS mutation, ECR push, email confirmation, RDS connection, migration, or GitHub push was performed while completing this root.

Final decision: **READY_FOR_STAGING_PREREQUISITES_PLAN_APPROVAL**.
