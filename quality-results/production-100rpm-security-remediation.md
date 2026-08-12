# Production 100 RPM security remediation

Date: 2026-08-12 UTC

## Notification blocker

Production alarms use the dedicated `ai-platform-prod-alerts` SNS topic. The planned email subscription is `info@nagi-neco.com`, protocol `email`, with `endpoint_auto_confirms = false`. AWS changes were not applied, so a human must confirm the subscription email after an approved apply. The staging topic remains the separate `system-navigator-staging-alerts`; the remediated Production plan contains zero staging actions.

## pip-audit root cause and remediation

The old quality image contained pip 25.0.1 and reported five findings against pip itself. They were bootstrap/test-image tooling findings, not vulnerabilities in the application requirements. pip-audit/OSV did not supply severity values.

| Advisory | CVE / GHSA | Package | Installed | Fixed | Severity | Scope | Dependency |
|---|---|---|---:|---:|---|---|---|
| PYSEC-2026-196 | CVE-2026-8643 / GHSA-wf93-45jw-7689 | pip | 25.0.1 | 26.1.2 | not supplied | quality/build tooling | direct bootstrap tool |
| PYSEC-2026-1795 | CVE-2025-8869 / GHSA-4xh5-x5gv-qwph | pip | 25.0.1 | 25.3 | not supplied | quality/build tooling | direct bootstrap tool |
| PYSEC-2026-1796 | CVE-2026-1703 / GHSA-6vgw-5pg2-w6jp | pip | 25.0.1 | 26.0 | not supplied | quality/build tooling | direct bootstrap tool |
| PYSEC-2026-2875 | CVE-2026-3219 / GHSA-58qw-9mgm-455v | pip | 25.0.1 | 26.1 | not supplied | quality/build tooling | direct bootstrap tool |
| PYSEC-2026-2876 | CVE-2026-6357 / GHSA-jp4c-xjxw-mgf9 | pip | 25.0.1 | 26.1 | not supplied | quality/build tooling | direct bootstrap tool |

The Docker build pins pip 26.1.2, the lowest common fixed version identified by the audit. The quality stage retains it for tests. The final runtime stage explicitly uninstalls pip and contains neither pip-audit nor other test/security tools. Runtime application requirements, entrypoint, health check, CPU and memory configuration are unchanged.

## Retest

- Entire remediated quality environment: pip-audit 0 known vulnerabilities.
- `requirements-runtime.txt`: pip-audit 0 known vulnerabilities.
- Ruff: PASS.
- Bandit: PASS, 0 findings.
- Repository secret scan: PASS, 0 findings.
- Backend: 128 passed; overall coverage 83.09%; critical-service coverage 90.86% (1560/1717).
- Frontend: 34 passed; production build PASS; OpenAPI check PASS.
- Terraform safety tests: 22 passed.
- Terraform fmt/validate: PASS for bootstrap, environment, staging and staging-prerequisites.
- Staging convergence plan: No changes.

No Terraform apply, AWS mutation, RDS connection, migration, Secret operation, image push or GitHub push was performed.
