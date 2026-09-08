# Staging custom domain runbook

The only approved staging application domain is `test.system-navigation.com`.
Authoritative DNS remains お名前.com (`dns1.onamae.com` / `dns2.onamae.com`), so
Terraform defaults to `dns_provider = "external"` and never changes external DNS.

## Two-phase plan

Phase A uses only `environment/staging-prerequisites`. Review a plan with the custom
domain enabled. It may create the eu-west-2 DNS-validated ACM certificate, but it
owns no ALB, ECS runtime, RDS, VPC, application Secret value, or Route53 record.
Do not apply it under a code-review-only authorization. After a separately approved
apply, copy `staging_acm_validation_records` (`domain`, `name`, `type`, `value`) into
お名前.com and wait until ACM reports `ISSUED`.

Phase B uses `environment/staging`. Keep `staging_mode = "idle"`,
`allow_staging_reactivation = false`, and `acm_certificate_issued = false` during
Phase A. Only after human verification of `ISSUED`, supply the prerequisite
`acm_certificate_arn`, set `acm_certificate_issued = true`, and enter the existing
separately reviewed active-reactivation process. Active mode creates the HTTPS 443
listener and makes HTTP 80 return a 301 redirect. `staging_alb_dns_name` is null in
idle mode and becomes the target for the final external CNAME in active mode.

## お名前.com DNS sequence

1. Review the Phase A ACM prerequisite plan.
2. After separately approved creation, obtain `staging_acm_validation_records`.
3. A human registers each ACM validation CNAME in お名前.com.
4. A human confirms that ACM is `ISSUED`; Terraform does not wait for external DNS.
5. Review the gated staging active plan, including ALB HTTPS, ECS, and RDS recovery.
6. Obtain `staging_alb_dns_name` from the reviewed active result/output.
7. Before adding the final CNAME, inspect the `test` owner in お名前.com. It is
   currently reported to have `A 150.95.255.38`, `TXT "v=spf1 -all"`, and `MX 0 .`;
   wildcard/parking records may also exist. A CNAME generally cannot coexist with
   other records at the same owner. A human must review and explicitly remove or
   change conflicts. Terraform must never delete those A/TXT/MX records.
8. A human sets `test.system-navigation.com CNAME <staging-alb-dns-name>`.
9. Verify HTTPS, the HTTP-to-HTTPS 301, frontend/backend same-host routing, and that
   CORS accepts only `https://test.system-navigation.com`.

The frontend keeps `NEXT_PUBLIC_API_BASE_URL=/api/v1`; no environment-specific
absolute API URL is embedded. Cognito remains disconnected. Track callback/logout
registration as `COGNITO_STAGING_DOMAIN_FOLLOW_UP` after real callback paths are
implemented (for example `https://test.system-navigation.com/<callback>`).

This runbook does not authorize Terraform apply, AWS or DNS writes, staging
reactivation, ECS deployment, RDS restore/create, Secret changes, database access,
or migrations.
