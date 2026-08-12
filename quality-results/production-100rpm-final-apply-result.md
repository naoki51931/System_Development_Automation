# Production 100 RPM final apply result — 2026-08-12 UTC

## Authorization and preflight

- Git HEAD: `f0ef87cbc29db964911ebf08a72072e49092f9b9`; worktree clean before apply.
- AWS: account `557604519341`, region `eu-west-2`, assumed role `instanceRoleTerraform`.
- State key: `cloud-a/prod/terraform.tfstate`.
- Saved plan: `environment/production-100rpm-pitr-remediated-final.tfplan`.
- SHA-256: `6c4a977c54942c734526abc7f233124014a74eef861fc298f91f90b28b27efc3`; exact match.
- Reviewed actions: 19 add / 3 change / 0 replace / 0 destroy; no IAM expansion or Staging action.
- PITR pre-apply: PASS with only `PITR_API_FIELD_WARNING` for null `DBInstance.EarliestRestorableTime`.
- Manual snapshot `ai-platform-prod-pre-100rpm-downsize-20260812-010957`: available, 100%, encrypted.
- Pre-apply GET `/`, `/health`, and `/docs`: HTTP 200; target healthy.

## Apply result

Terraform applied the ECS downsizing, autoscaling, SNS subscription, seven ALB/ECS alarms, and Container Insights update. The RDS update failed with AWS `InsufficientDBInstanceCapacity`: the requested Multi-AZ `db.t4g.small` capacity was not available across enough Availability Zones. Terraform exited nonzero. No retry, `apply-immediately`, permission change, manual rollback, or other mutation was performed.

Observed successful actions are 13 creates and 2 in-place changes. Observed remaining actions are 6 creates and 1 in-place RDS change; replacement and destruction remain zero.

## Post-apply state

| Area | Result |
|---|---|
| ECS task | `ai-platform-prod:4` → `ai-platform-prod-low-traffic:1` |
| ECS capacity | 512 CPU / 1024 MiB → 256 CPU / 512 MiB |
| ECS service | desired 1, running 1, pending 0; deployment COMPLETED |
| Auto Scaling | min 1, max 2; CPU target 60%, memory target 70% |
| Smoke | `/`, `/health`, `/docs` all HTTP 200; health body `{"status":"ok"}` |
| Target health | new target healthy; replaced target observed draining normally |
| RDS | available; remains `db.t4g.medium`; no pending modification |
| RDS safety | Multi-AZ true, 50 GiB gp2, retention 14, deletion protection/encryption true, public false |
| Maintenance | `sat:02:43-sat:03:13`; not classified as maintenance-pending because AWS rejected the modification |
| PITR post-apply | PASS; same DBInstance warning only |
| Manual snapshot | available, encrypted, retained |
| ALB / NAT | active / available |
| Alarms | 7 present, all OK: ALB 4 and ECS 3; required RDS 6 are absent |
| SNS | `ai-platform-prod-alerts`; `info@nagi-neco.com`; PendingConfirmation |
| Staging | RDS 0, ALB 0, Interface Endpoints 0, runtime ECS 0; `STAGING_IDLE_MODE_CONVERGED` |
| Post-apply plan | detailed exit 2; 6 add / 1 change / 0 destroy (RDS class plus six RDS alarms) |

The observed ECS CPU and memory alarm datapoints were approximately 1.25–1.28% and 5.18%; ALB p95 was approximately 2 ms, target/ELB 5xx alarms were OK, and unhealthy-host count was zero before the old target entered normal draining.

## Cost and decision

The target fully-remediated estimate remains approximately $135–136/month from approximately $192/month, saving $56–57/month; combined with the prior Staging reduction the target remains $262–265/month. That full Production estimate is **not yet active** because RDS remains `db.t4g.medium`; resource configuration, not Cost Explorer, is the primary evidence.

Final decision: **PRODUCTION_100RPM_DOWNSIZING_REQUIRES_REMEDIATION**.

Human actions required:

1. Confirm the SNS subscription email sent to `info@nagi-neco.com`.
2. After AWS Multi-AZ `db.t4g.small` capacity is available, generate and review a fresh remediation plan for the remaining RDS update and six alarms, then obtain separate apply approval. Do not reuse or reapply the partially consumed saved plan without a new review.
