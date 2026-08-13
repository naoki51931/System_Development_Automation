# Staging prerequisites

This independent Terraform root owns only the two staging ECR repositories, the GitHub staging deploy role and policy, the staging SNS topic/email subscription, and the 150 USD staging Budget. AWS Budgets rejected the former 100 GBP setting because this account accepts USD only. Its state key is `system-navigator/staging/prerequisites.tfstate`. Custom-domain ACM and DNS validation are conditional and disabled by default; no domain is selected.

It does not own or read the main staging VPC, endpoints, RDS, ECS cluster/services/tasks, ALB, artifact bucket, application Secrets, or a final Route53 alias. Pass ECR URLs, deploy-role ARN, and SNS topic ARN explicitly into the main staging root. A certificate ARN is supplied only after a separately approved replacement domain exists. The dependency direction is prerequisites to staging only.

The SNS subscription remains `PendingConfirmation` until a human confirms the AWS email. Budget creation is independently gated by `enable_budget`; it defaults to false and, after separate approval, Budget notifications are sent directly by AWS Budgets rather than through SNS. Never commit `backend.hcl`, `terraform.tfvars`, plans, state, or secret values.
