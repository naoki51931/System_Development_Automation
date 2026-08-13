# Staging prerequisites Terraform plan review

- Plan timestamp: `2026-08-09T08:34:15Z`
- Git commit: `90288e2a03eb0caa807a12ade0020689a73c1370`
- AWS account: `557604519341`
- Region: `eu-west-2`
- State bucket: `ai-platform-terraform-state-557604519341`
- State key: `system-navigator/staging/prerequisites.tfstate`
- Existing state resources: `0` (no state file existed)

## Plan summary

The saved plan is add-only: **12 add, 0 change, 0 replace, 0 destroy**, plus one local IAM policy-document data read deferred until ECR ARNs are known. No production term or prohibited resource type occurs in `resource_changes`.

| Address | Action |
|---|---|
| `module.deploy_role.aws_iam_role.deploy` | create |
| `module.deploy_role.aws_iam_role_policy.deploy` | create |
| `module.dns.aws_acm_certificate.staging` | create |
| `module.dns.aws_acm_certificate_validation.staging` | create |
| `module.dns.aws_route53_record.validation["staging.true-camera-test.com"]` | create |
| `module.ecr.aws_ecr_repository.staging["system-navigator-staging-app"]` | create |
| `module.ecr.aws_ecr_repository.staging["system-navigator-staging-frontend"]` | create |
| Two matching `aws_ecr_lifecycle_policy` resources | create |
| `module.notifications.aws_sns_topic.alerts` | create |
| `module.notifications.aws_sns_topic_subscription.email` | create |
| `module.notifications.aws_budgets_budget.monthly` | create |

## Scope review

- ECR: exactly `system-navigator-staging-app` and `system-navigator-staging-frontend`; immutable tags, scan-on-push, AES256, `force_delete=false`, untagged seven-day and tagged-generation lifecycle rules. No `latest` image is referenced.
- IAM: role `system-navigator-staging-github-deploy`. Trust is `aud=sts.amazonaws.com` and `sub=repo:naoki51931/System_Development_Automation:environment:staging`; no wildcard trust or AdministratorAccess.
- IAM wildcard resource exception: only `ecr:GetAuthorizationToken` and `ecs:RegisterTaskDefinition`, whose AWS authorization models do not support useful resource-level restriction. All ECR push, ECS service/task-definition, `iam:PassRole`, logs, S3 state, and KMS permissions are staging-scoped.
- State access: bucket listing is conditioned to `system-navigator/staging/*`; object access is restricted to the same prefix. `cloud-a/prod` is absent. KMS access is restricted to the configured state key.
- ACM/Route53: one eu-west-2 DNS-validated certificate for `staging.true-camera-test.com` and its validation record in zone `Z05220783EQSOCLA4YS4T`. No ALB alias or production record is present.
- SNS: `system-navigator-staging-alerts`, email protocol, approved variable endpoint, and `endpoint_auto_confirms=false`. After apply it remains `PendingConfirmation` until a human confirms the message sent to `info@nagi-neco.com`.
- Budget: `system-navigator-staging-monthly`, 100 GBP monthly, actual 50/80/100% and forecasted 100%, sent directly by AWS Budgets to `info@nagi-neco.com` rather than through SNS.
- Excluded: VPC, subnet, NAT, endpoint, RDS, ECS cluster/service/task definition, ALB/target group, artifact S3, Secrets, Cognito and SES.

## Production impact and IAM risk

Production changes are **zero**. JSON searches for `ai-platform-prod`, `cloud-a/prod`, and `production` returned zero in resource changes. Change, replace and destroy counts are zero. IAM risk is limited to the two documented unscopable actions; trust, PassRole, ECR, ECS, logs, state and KMS scopes are staging-specific.

## Cost classification

| Service | Classification | Impact |
|---|---|---|
| ECR | 継続・従量課金 | Stored image bytes and scanning/data transfer can incur charges; lifecycle limits retention. |
| IAM | 基本無料 | Role and inline policy have no direct recurring charge. |
| Public ACM certificate | 基本無料 | AWS public certificate has no certificate charge; associated future load balancer is outside this plan. |
| Route53 validation record | 継続・従量課金 | Existing hosted-zone billing remains; DNS queries may be metered. No new hosted zone. |
| SNS | 従量課金・通知確認 | Topic delivery is usage-based; email subscription requires manual confirmation. |
| AWS Budget | 基本無料/サービス条件依存 | Budget monitoring itself has no infrastructure runtime; account pricing/limits still apply. |

VPC, endpoints, NAT, RDS, ECS and ALB are not in this plan, so their runtime costs are not introduced here.

## Human actions after a separately approved apply

1. Confirm the SNS subscription from the email delivered to `info@nagi-neco.com`; no automatic confirmation exists.
2. Confirm ACM reaches `ISSUED` after the DNS validation record resolves.
3. Confirm GitHub Environment `staging` protection and approved branches/reviewers before using OIDC.
4. Verify the four Budget notification rules and recipient.
5. Separately approve ECR push and require scan results before capturing registry digests.

## Apply stop conditions

Do not approve apply if any refreshed plan has destroy, replace or update actions; production changes/state permissions; anything other than two staging ECR repositories; wildcard GitHub trust; AdministratorAccess; broader PassRole; wrong domain, zone, email or Budget; production DNS changes; or any unexpected resource type. Apply must use the reviewed saved plan only after a new explicit human approval.

## Rollback considerations

No rollback was executed. If a later approved apply must be reversed, first disable GitHub Environment access and active sessions, preserve evidence, and create a separately reviewed destroy plan. Unsubscribe SNS manually if required, remove DNS validation only after certificate dependencies are gone, and retain ECR repositories while images are referenced; `force_delete=false` intentionally prevents accidental deletion of non-empty repositories. Budget deletion and IAM removal require separate impact review.

## Decision

**READY_FOR_STAGING_PREREQUISITES_APPLY_APPROVAL**. This review does not authorize apply.
