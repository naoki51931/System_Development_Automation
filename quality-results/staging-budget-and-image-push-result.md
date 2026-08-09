# Staging Budget and image-push result

- Timestamp: `2026-08-09T10:51:27Z`
- Git HEAD: `f1876f00cf7e75ae6cdd54729a76d92156eda92c`
- AWS account: `557604519341`
- Region: `eu-west-2`

## Phase A: SNS confirmation

`system-navigator-staging-alerts` exists and its email endpoint is the approved monitoring address. The subscription remains `PendingConfirmation`, so `SNS_EMAIL_CONFIRMATION=BLOCKED` pending a human opening the AWS confirmation email. No confirmation link was opened automatically.

## Phase B: Budget

The reviewed saved plan `environment/staging-prerequisites/enable-staging-budget.tfplan` contained exactly **1 add, 0 change, 0 replace, 0 destroy**. The only action was creation of `system-navigator-staging-monthly` with the requested 100 GBP monthly limit and four notification rules. ECR, IAM and SNS were no-op, and production impact was zero.

Applying that saved plan failed without creating the Budget. AWS Budgets returned `InvalidParameterException`: this account supports the unit set `[USD]`, so `GBP` was rejected. Terraform state remains unchanged and an AWS read confirms that the Budget does not exist. No permission was broadened and the currency was not changed automatically.

The post-apply convergence plan was not run because apply did not succeed. With the approved GBP input unchanged, the saved Budget create remains unapplied.

## Phase C: ECR image push

Not started. The workflow requires a successful Budget phase before image build, ECR login, push, digest capture, and scan. Therefore:

- Image tag: not generated for a build/push
- App image push/digest/scan: not performed
- Frontend image push/digest/scan: not performed
- Main staging ignored tfvars digest update: not performed

No ECR image, GitHub branch, main staging infrastructure, RDS, ECS service, ALB, or migration was changed.

## Decision

**NOT_READY_FOR_MAIN_STAGING_PLAN_APPROVAL**. Human input is required to decide whether the Budget may use USD and, if so, the approved USD amount. SNS email confirmation also remains a manual prerequisite.
