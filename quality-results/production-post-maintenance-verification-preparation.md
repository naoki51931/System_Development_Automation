# Production post-maintenance verification preparation — 2026-08-12 UTC

AWS identity was confirmed as account `557604519341`, region `eu-west-2`, role `instanceRoleTerraform`, from clean HEAD `8c02e93ff0480cb1efc992c3091acb4f99b7fa95`.

The read-only verifier is `scripts/verify_production_100rpm_post_maintenance.py`. It uses only AWS `describe-*`/`list-*` calls, HTTP GET, and the existing PITR Gate. It contains no create, modify, put, update, delete, restore, reboot, start or stop operation. Run after the maintenance window:

```bash
python3 scripts/verify_production_100rpm_post_maintenance.py \
  --region eu-west-2 \
  --alb-url http://ai-platform-prod-1767582825.eu-west-2.elb.amazonaws.com
```

It requires RDS `db.t4g.small`, available/no pending class, Multi-AZ, 50 GiB gp2, retention 14, deletion protection/encryption, and private access. It reuses the PITR Gate, checks the retained encrypted manual snapshot, ECS 256/512 and 1/1 healthy deployment, GET `/`, `/health`, `/docs`, 13 alarms split 4/3/6, Production SNS/email status, ALB/NAT, and Staging idle. An ALARM does not hide the remaining evidence; it emits `POST_MAINTENANCE_ALARM_REVIEW_REQUIRED`. Pending SNS emits `MANUAL_SNS_CONFIRMATION_REQUIRED`.

The pre-maintenance dry run collected all evidence and failed exactly on `RDS_DBINSTANCECLASS_INVALID` and `RDS_CLASS_STILL_PENDING`, as intended. Current RDS is available medium with small pending for `sat:02:43-sat:03:13`; PITR passes, snapshot is available/encrypted, ECS is healthy, all three GETs are 200, all 13 alarms are OK, and SNS subscription is Confirmed.

Unit/security verification: 28 PITR/post-maintenance tests passed; Ruff, formatting, Bandit and compileall passed; secret scan passed.

## Terraform convergence procedure

After maintenance, from `environment/`:

```bash
terraform init -reconfigure -backend-config=backend.hcl
terraform plan -var-file=terraform.tfvars \
  -out=production-post-maintenance-convergence.tfplan
terraform show -no-color production-post-maintenance-convergence.tfplan
```

Never apply this convergence plan as part of verification. Before maintenance, the generated review plan is 0 add / 1 in-place RDS class change / 0 replace / 0 destroy, matching AWS pending maintenance. After maintenance the required result is 0/0/0/0. Any other action is `POST_MAINTENANCE_TERRAFORM_DRIFT_REVIEW_REQUIRED`.

Decision: **PRODUCTION_POST_MAINTENANCE_VERIFICATION_READY**.
