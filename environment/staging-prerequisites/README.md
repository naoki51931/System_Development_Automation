# Staging prerequisites

This independent Terraform root owns only the two staging ECR repositories, the GitHub staging deploy role and policy, the staging SNS topic/email subscription, the 150 USD staging Budget, and the approved `test.system-navigation.com` ACM prerequisite. AWS Budgets rejected the former 100 GBP setting because this account accepts USD only. Its state key is `system-navigator/staging/prerequisites.tfstate`. DNS defaults to external お名前.com management; Terraform outputs validation records and creates no Route53 records in that mode.

It does not own or read the main staging VPC, endpoints, RDS, ECS cluster/services/tasks, ALB, artifact bucket, application Secrets, or a final external DNS CNAME. Pass ECR URLs, deploy-role ARN, SNS topic ARN, and the certificate ARN explicitly into the main staging root only after a human confirms ACM is `ISSUED`. The dependency direction is prerequisites to staging only. See `docs/staging_custom_domain.md`.

The SNS subscription remains `PendingConfirmation` until a human confirms the AWS email. Budget creation is independently gated by `enable_budget`; it defaults to false and, after separate approval, Budget notifications are sent directly by AWS Budgets rather than through SNS. Never commit `backend.hcl`, `terraform.tfvars`, plans, state, or secret values.
