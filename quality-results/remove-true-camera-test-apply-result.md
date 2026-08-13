# Deprecated staging domain removal result

- Timestamp: `2026-08-09T10:45:00Z`
- Git HEAD applied from: `fdfbbc59ad954709ded31d14f9095bec3571f588`
- AWS account: `557604519341`
- Region: `eu-west-2`
- State key: `system-navigator/staging/prerequisites.tfstate`
- Applied saved plan: `environment/staging-prerequisites/remove-true-camera-test-only.tfplan`

## Apply result

Terraform completed successfully: **0 added, 0 changed, 3 destroyed**. The destroyed Terraform addresses were the unused ACM certificate, its certificate-validation completion resource, and the corresponding Route53 ACM validation CNAME. No replacement plan was generated and no other saved plan was applied.

## Final resource state

- ACM: the rejected historical staging certificate is absent from eu-west-2.
- Route53: the matching ACM validation CNAME is absent; no other record was targeted by the saved plan.
- ECR: both staging repositories and both lifecycle policies remain in state. AWS reports immutable tags, scan-on-push, and AES256 encryption.
- IAM: `system-navigator-staging-github-deploy` and its `staging-deploy` inline policy remain present.
- SNS: `system-navigator-staging-alerts` and its email subscription remain present. The subscription remains `PendingConfirmation` for the approved monitoring address.
- Budget: `system-navigator-staging-monthly` remains absent. The apply contained no Budget action and `enable_budget=false` remains configured.
- Production: the reviewed plan contained no production identifier or action; apply reported only the three approved destroys.

Terraform state no longer contains the ACM certificate, ACM validation completion resource, or Route53 validation record. Active Terraform configuration and examples contain zero references to the rejected domain or hosted zone. Documentation and historical quality evidence may retain the name only to record its rejection and removal.

## Convergence and warnings

The post-apply command `terraform plan -var-file=terraform.tfvars -detailed-exitcode` returned **No changes** with exit code `0`. Custom domain and Budget creation remain disabled. No ECR push, Budget creation, main staging plan/apply, RDS/ECS operation, migration, or GitHub push occurred.

The SNS email subscription still requires human confirmation; this is expected and was not modified. No other warning remains.

## Decision

**READY_FOR_STAGING_PREREQUISITE_CONTINUATION**.
