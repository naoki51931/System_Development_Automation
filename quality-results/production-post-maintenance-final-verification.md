# Production post-maintenance final verification — 2026-08-12 UTC

No AWS resource was changed. Identity was account `557604519341`, region `eu-west-2`, role `instanceRoleTerraform`; the start worktree was clean at `4429e3bf5d454fc616af89ee2c8e6af0f5e035b3`.

## Result

The RDS maintenance change has **not completed**. `ai-platform-prod-postgres` is `available` on `db.t4g.medium`, with `PendingModifiedValues.DBInstanceClass=db.t4g.small`. Its safety properties remain Multi-AZ, 50 GiB gp2, retention 14, deletion protection and encryption enabled, public access disabled, with maintenance window `sat:02:43-sat:03:13`.

The existing read-only verifier failed only with `RDS_DBINSTANCECLASS_INVALID` and `RDS_CLASS_STILL_PENDING`, which is the intended fail-closed behavior before maintenance completes. All other observations passed:

- PITR `PASS`; only `PITR_API_FIELD_WARNING` for null `DBInstance.EarliestRestorableTime`.
- Manual snapshot `ai-platform-prod-pre-100rpm-downsize-20260812-010957` is available and encrypted.
- ECS `ai-platform-prod-low-traffic:1` is 256 CPU / 512 MiB, desired/running/pending `1/1/0`, deployment `COMPLETED`, target healthy. Auto Scaling is min/max `1/2`; CPU target is 60% and memory target is 70%.
- GET `/`, `/health`, and `/docs` returned HTTP 200.
- 13 alarms are present: ALB 4, ECS 3, RDS 6. All 13 are `OK`; none is `ALARM` or `INSUFFICIENT_DATA`.
- SNS `ai-platform-prod-alerts` endpoint `info@nagi-neco.com` is Confirmed.
- ALB is active, NAT is available, and Staging remains idle with RDS/ALB/interface endpoints/runtime ECS all zero.

The fresh plan `environment/production-post-maintenance-final-convergence.tfplan` was created from `cloud-a/prod/terraform.tfstate` and reviewed without apply. SHA-256 is `9d19de52c105ce9da98b9ce4ba43f62c967bbc66ab4eea8869867ef8e59b9e5f`. It is 0 add / 1 in-place change / 0 replace / 0 destroy; the sole change is RDS `db.t4g.medium -> db.t4g.small`. This is consistent with the pending maintenance modification, but it is not the required post-maintenance no-op.

The PITR and post-maintenance unit suites passed (28 tests). Ruff check/format, Bandit, compileall, pip-audit (0 known vulnerabilities), and the repository secret scan passed. The quality image reports pip `26.1.2`.

Expected configuration-based cost remains approximately `$183–184/month` until RDS becomes small and `$135–136/month` afterward. Final Production saving remains approximately `$56–57/month`; combined with Staging it remains approximately `$262–265/month`. Cost Explorer can lag the configuration and was not used to override observed resource state.

Decision: **RDS_DOWNSIZING_STILL_PENDING_MAINTENANCE**. `PRODUCTION_100RPM_DOWNSIZING_ACTIVE` and `TERRAFORM_CONVERGENCE_NOOP` are not yet satisfied. Re-run the read-only verifier and fresh convergence plan after AWS clears the pending class and reports `db.t4g.small`; do not apply the convergence plan.
