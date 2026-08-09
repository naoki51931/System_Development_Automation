# Staging prerequisites

This independent Terraform root owns only the two staging ECR repositories, the GitHub staging deploy role and policy, the staging ACM certificate and DNS validation records, the staging SNS topic/email subscription, and the 100 GBP staging Budget. Its state key is `system-navigator/staging/prerequisites.tfstate`.

It does not own or read the main staging VPC, endpoints, RDS, ECS cluster/services/tasks, ALB, artifact bucket, application Secrets, or the final Route53 alias. After an approved prerequisites apply, pass the ECR URLs, deploy-role ARN, certificate ARN, and SNS topic ARN explicitly into the main staging root. The dependency direction is prerequisites to staging only.

The SNS subscription remains `PendingConfirmation` until a human confirms the AWS email. Budget notifications are sent directly by AWS Budgets, not through SNS. Never commit `backend.hcl`, `terraform.tfvars`, plans, state, or secret values.
