# Production NAT Gateway cost read-only analysis — 2026-08-12 UTC

No AWS or Terraform resource was changed. This analysis uses current AWS inventory, 14-day CloudWatch NAT metrics, Cost Explorer for 2026-07-12 through 2026-08-12, and AWS Pricing API publication `2026-08-10`.

## Inventory and routing

- NAT `nat-041c10f70dc672ab4` is available/public in VPC `vpc-0da4eaf0768153c5c`, public subnet `subnet-039582b5311a27894` (`eu-west-2a`), with EIP allocation `eipalloc-091bbb181085cb162`.
- Route table `rtb-04bc5b9c3ddd5a849` sends `0.0.0.0/0` to this NAT for app private subnets `subnet-0b224e86387598728` (`10.20.10.0/24`, eu-west-2a) and `subnet-0b0528c6af4fecff9` (`10.20.11.0/24`, eu-west-2b).
- Database subnets `10.20.20.0/24` and `10.20.21.0/24` use the main local-only route table and do not depend on NAT. Public subnets use the Internet Gateway.
- Production has zero VPC endpoints and zero VPC Flow Logs. Destination-level attribution therefore cannot be proven from retained network logs.

The ECS task has no public IP, uses both app private subnets and `awsvpc`, pulls `ai-platform-prod:v4` from ECR and writes to `/ecs/ai-platform-prod` through `awslogs`. Its only environment name is `APP_ENV`; it has no secret references, no task-role policy and no configured external provider credential. The execution role has the standard ECS execution policy. Security-group egress permits all IPv4.

Confirmed NAT-dependent AWS paths are ECR API, ECR DKR, ECR layer download through S3, and CloudWatch Logs. Secrets Manager, STS, KMS and CloudWatch Monitoring endpoints are not required by the current task definition. No external AI/payment/email/SMTP or other Internet dependency is configured in the deployed task, but unrestricted egress plus absent Flow Logs means unknown runtime Internet use cannot be conclusively excluded.

Fourteen-day NAT metrics show approximately 84.8 MB from destination and 13.8 MB toward destination (about 0.079 GiB processed in the larger direction). Data processing is negligible; fixed hourly cost dominates.

## Current pricing and options

AWS Pricing API London rates are NAT `$0.05/hour` and `$0.05/GB`, Interface Endpoint `$0.011/AZ-hour`, and public IPv4 `$0.005/hour`. At 730 hours/month:

| Option | Architecture | Relevant monthly cost | Saving vs A | Assessment |
|---|---|---:|---:|---|
| A | Current NAT + public IPv4 | ~$40.16 (`$36.50` NAT + `$3.65` IPv4 + `<$0.01` data) | — | Lowest safe current design; single-AZ NAT is an availability dependency |
| B | NAT + free S3 Gateway Endpoint | ~$40.15–40.16 | `<$0.01` at observed traffic | Technically useful but financially immaterial; does not remove ECR API/DKR/Logs NAT need |
| C | Remove NAT; S3 Gateway + ECR API/DKR/Logs Interface Endpoints in two AZs | ~$48.18 plus negligible endpoint data | **-$8.02** (cost increase) | Technically possible for confirmed dependencies, but not cost-effective |

Two-AZ minimum private replacement requires 6 endpoint-AZ hours: `3 × 2 × $0.011 × 730 = $48.18/month`. Adding Secrets Manager, STS, KMS or Monitoring would add about `$16.06/month` each and is not justified by current task configuration. A one-AZ endpoint design is rejected because it would weaken availability and can add cross-AZ traffic.

S3 Gateway Endpoint has no hourly charge and can reduce S3-related NAT processing, but the maximum observed monthlyized NAT processing saving is below one cent. Cost Explorer is account-wide and the queried period includes resources created partway through the month, so its partial figures are not a steady-state Production allocation; configuration and Pricing API rates are the primary evidence.

Production remains approximately $183–184/month while RDS small is pending and approximately $135–136/month after maintenance. Option B leaves the post-RDS estimate effectively unchanged. Option C raises it to approximately $143–144/month. Combined Staging + Production saving remains approximately $262–265/month with Option A/B.

The separate work instance `i-0add395a2d89805b5` is running `t3.medium` with one unencrypted 30 GiB gp3 volume and a public IPv4. At current London on-demand rates it is approximately `$34.46` compute + `$2.78` storage + `$3.65` IPv4 = **$40.89/month**, excluding CPU credit and transfer variation. It is outside Production Terraform scope; stopping or storage remediation requires separate approval.

## Decision

There is no confirmed external Internet API requirement, so NAT removal is technically possible for the known workload with private AWS endpoints. It is not cost-effective: minimum endpoint fixed cost exceeds NAT plus IPv4 by about $8/month, while NAT data processing is negligible.

Decision: **PRODUCTION_NAT_REMOVAL_NOT_COST_EFFECTIVE**.

Recommended architecture: retain the NAT and current private task placement. A future S3 Gateway Endpoint may be reviewed as a security/routing improvement, not a meaningful cost saving. Before any NAT removal proposal, enable separately approved Flow Logs or equivalent destination evidence and observe a representative period; then reassess external egress and endpoint count. No NAT/VPC Terraform change is proposed now.
