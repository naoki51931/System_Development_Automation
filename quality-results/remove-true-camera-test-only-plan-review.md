# Domain-only Terraform removal plan review

- Git HEAD used for planning: `1500c52ed7414f786ddbf6fb41acdde6b92ff32d`
- AWS account: `557604519341`
- Region: `eu-west-2`
- State key: `system-navigator/staging/prerequisites.tfstate`
- Saved plan: `environment/staging-prerequisites/remove-true-camera-test-only.tfplan`

## Plan result

```text
0 to add
0 to change
0 to replace
3 to destroy
```

The three Terraform destroys are exclusively:

1. The unused ACM certificate for the rejected historical staging domain.
2. The ACM certificate-validation completion resource in Terraform state.
3. The corresponding Route53 ACM validation CNAME.

The ACM certificate is currently `ISSUED` with an empty `InUseBy` list. Exactly one matching validation CNAME currently exists. These historical identifiers are retained in this document solely to identify deletion targets; they are not active SystemNavigator AI configuration.

## Preserved resources

- ECR repositories and lifecycle policies: four managed resources, all `no-op`.
- GitHub staging deploy role and inline policy: two managed resources, both `no-op`.
- SNS alerts topic and email subscription: two managed resources, both `no-op`; subscription remains `PendingConfirmation` for `info@nagi-neco.com`.
- Budget: no AWS Budget exists. `enable_budget=false` produces no create/change/destroy action. The 100 GBP design remains available for a later, separate approval.
- Production: no production identifier or resource change occurs.

## Configuration boundaries

`enable_custom_domain=false` remains active, with empty domain and hosted-zone inputs. No replacement domain is inferred. `enable_budget=false` isolates this removal from Budget creation while leaving SNS independent and unchanged.

## Apply stop conditions

Do not apply if a regenerated or stale-plan check shows any add, change, replacement, more than three destroys, an ACM certificate in use, or any ECR, IAM, SNS, Budget, staging runtime, state-backend, or production action. Apply must use this reviewed saved plan only after explicit human approval.

## Decision

**READY_FOR_TRUE_CAMERA_TEST_RESOURCE_REMOVAL_APPLY**. No apply or manual AWS deletion was executed during this review.
