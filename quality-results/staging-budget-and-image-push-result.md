# Staging Budget and image-push result

- Timestamp: `2026-08-09T11:08:00Z`
- Image source Git HEAD: `a5d22280475a729b8b174d4f23a4597e7d89fac3`
- Image tag: `a5d22280475a`
- AWS account: `557604519341`
- Region: `eu-west-2`

## Phase A: SNS confirmation

`system-navigator-staging-alerts` exists and points to the approved monitoring address. The subscription remains `PendingConfirmation`, so `SNS_EMAIL_CONFIRMATION=BLOCKED` until a human opens the AWS confirmation email. No confirmation link was opened automatically.

## Phase B: Budget

AWS Budgets rejected the former 100 GBP setting because this account accepts USD only. Terraform validation now permits only USD and fixes the approved staging amount at 150.

The reviewed saved plan `environment/staging-prerequisites/enable-staging-budget-usd.tfplan` contained exactly **1 add, 0 change, 0 replace, 0 destroy**. Its only action created `system-navigator-staging-monthly`; ECR, IAM and SNS were no-op and production impact was zero.

Apply succeeded. AWS reports a 150 USD monthly cost Budget with Actual 50%, Actual 80%, Actual 100%, and Forecasted 100% notifications. All four notifications use the approved monitoring email. The post-apply Terraform plan returned `No changes` with exit code 0.

## Phase C: ECR images

Both linux/amd64 images were rebuilt from the recorded source commit with `--pull`, non-root runtime users, expected commands, and healthchecks. Only the immutable source tag was pushed; `latest` was not used.

- App repository: `system-navigator-staging-app`
- App registry digest: `sha256:4f998698fc78e37c46695c793d0fe1e9f01c1eac095fddf0ec772836bb818c50`
- App scan: `COMPLETE`; CRITICAL 4, HIGH 8, MEDIUM 5
- Frontend repository: `system-navigator-staging-frontend`
- Frontend registry digest: `sha256:5c2eeeee402293fa783c9a6dd67b6f03dce00b3651ef73d314f773d3371e82dc`
- Frontend scan: `COMPLETE`; CRITICAL 0, HIGH 0

The app scan violates the required zero-CRITICAL/zero-HIGH gate. Therefore `IMAGE_APPROVAL=FAIL`, and no digest URI was written to main staging tfvars. The pushed images remain staging candidates only and must not be deployed.

No GitHub push, main staging plan/apply, RDS, ECS deployment, ALB creation, migration, Cognito, Stripe, SES, or production change occurred.

## Decision

**NOT_READY_FOR_MAIN_STAGING_PLAN_APPROVAL**. Remediate and rebuild the app image until its registry scan reports CRITICAL 0 and HIGH 0. SNS email confirmation also remains a manual prerequisite.
