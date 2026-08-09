# Deprecated staging domain removal plan review

- Review timestamp: `2026-08-09T10:18:00Z`
- Git HEAD at discovery: `6b595cd706d2511acd0450f8c0800115f4501d05`
- AWS account: `557604519341`
- Region: `eu-west-2`
- Terraform state key: `system-navigator/staging/prerequisites.tfstate`

## Current AWS and Terraform state

The interrupted prerequisites apply created both ECR repositories and lifecycle policies, the GitHub deploy role and inline policy, an issued but unused staging ACM certificate, its successful Route53 validation CNAME, the SNS topic, and an email subscription that remains `PendingConfirmation`. AWS Budgets reports that `system-navigator-staging-monthly` does not exist, and it is absent from Terraform state.

The deprecated domain and hosted-zone identifiers below are recorded only as removal evidence; they are not approved current configuration. No replacement domain has been selected. The ACM certificate is `ISSUED`, has no `InUseBy` dependencies, and the matching validation CNAME exists in the former hosted zone.

## Configuration decision

Both Terraform roots default to `enable_custom_domain = false`. The prerequisites DNS module has count zero, so it requests no certificate or validation record and domain/zone inputs may be empty. Main staging creates no Route53 alias, requires no ACM ARN, enables no HTTPS listener, and outputs the ALB HTTP DNS URL. HTTP is temporary and prohibited for production, customer access, Stripe/Cognito/real authentication, and sensitive data.

The monitoring address remains `info@nagi-neco.com`. ECR, IAM, SNS and the approved 100 GBP Budget configuration are unchanged.

## Saved plan

- File: `environment/staging-prerequisites/remove-true-camera-test.tfplan`
- Human-readable file: `environment/staging-prerequisites/remove-true-camera-test-plan.txt`
- Summary: **1 add, 0 change, 0 replace, 3 destroy**
- Production changes: **0**

| Address | Action | Review |
|---|---|---|
| `module.dns.aws_acm_certificate.staging` | destroy | Removes the unused certificate. |
| `module.dns.aws_acm_certificate_validation.staging` | destroy | Removes only Terraform's validation-completion state object; it is not a separate billable AWS resource. |
| `module.dns.aws_route53_record.validation[...]` | destroy | Removes the ACM validation CNAME only. |
| `module.notifications.aws_budgets_budget.monthly` | create | The interrupted apply never created the approved 100 GBP Budget; this is not a domain resource. Explicitly review this add before removal apply approval. |

## Preserved scope

- ECR: both repositories and both lifecycle policies are `no-op`; destroy/change/replace = 0.
- IAM: deploy role and inline policy are `no-op`; destroy/change/replace = 0.
- SNS: topic and pending email subscription are `no-op`; destroy/change/replace = 0.
- Budget: destroy/change/replace = 0. One create remains because the interrupted apply did not create it.
- Production: no production name, state key, ARN, update, replacement or destroy occurs.

## Approval boundary

No apply or manual deletion was executed. A human removal approval must cover exactly the two AWS deletions (unused ACM certificate and its validation CNAME), removal of the Terraform validation state object, and the separately visible creation of the already approved 100 GBP staging Budget. If Budget creation is not intended in the same apply, this saved plan must not be approved and the workflow must be redesigned without using a routine target operation.

## Decision

**READY_FOR_TRUE_CAMERA_TEST_RESOURCE_REMOVAL_APPROVAL**, subject to explicit human review of the one Budget create alongside the three Terraform destroys. ECR, IAM, SNS and production remain untouched.
