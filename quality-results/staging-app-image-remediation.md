# Staging app image vulnerability remediation

## Previous image

- Source tag: `a5d22280475a`
- Registry digest: `sha256:4f998698fc78e37c46695c793d0fe1e9f01c1eac095fddf0ec772836bb818c50`
- ECR basic scan: CRITICAL 4, HIGH 8, MEDIUM 5

All CRITICAL/HIGH findings came from OS packages inherited from the floating `python:3.12-slim` base, which had moved to Debian Trixie. ECR did not report a fixed-package version or dependency path; Docker inspection confirmed the affected installed packages and that no application pip package produced these findings.

| Package / installed version | Severity | CVEs | Classification and exposure summary |
|---|---|---|---|
| Perl `5.40.1-6` | CRITICAL | CVE-2026-12087, CVE-2026-57433, CVE-2026-13221 | A/F: inherited OS runtime package, unused by the Python service; heap read, crafted deserialization termination, and incorrect regex decisions. |
| Perl `5.40.1-6` | HIGH | CVE-2026-57432, CVE-2026-7017, CVE-2026-48961, CVE-2026-48959, CVE-2026-48962 | A/F: inherited OS runtime package, unused by the service; heap read, cross-origin credential forwarding, CLI crash, CPU exhaustion, and output-glob code execution. |
| glibc `2.41-12+deb13u3` | CRITICAL | CVE-2026-5450 | A/B: inherited C runtime used by Python; crafted `scanf` width can overflow a heap buffer. |
| glibc `2.41-12+deb13u3` | HIGH | CVE-2026-5928 | A/B: inherited C runtime; special wide-character pushback can under-read a buffer. |
| SQLite `3.46.1-7+deb13u1` | HIGH | CVE-2026-11822, CVE-2026-11824 | A/F: inherited `libsqlite3`; staging uses PostgreSQL, but Python exposes SQLite support. Crafted FTS5 databases can corrupt memory. |

There were no C/D findings in direct or transitive pip dependencies: `pip-audit -r requirements-runtime.txt` reported no known vulnerabilities. No E build-only compiler, make, git, curl, or development package existed in the runtime image.

## Remediation

Python remains on 3.12.13. A first remediated build pinned Bookworm, which removed the glibc and SQLite findings but ECR still found CRITICAL 3 / HIGH 5 in its essential `perl-base`; Debian Trixie retained the same vulnerable Perl family. The final candidate therefore pins the official `python:3.12-alpine` linux/amd64 digest on Alpine 3.24.1. It contains no Perl and carries `sqlite-libs 3.53.2-r0`. The Alpine compatibility change is accepted only after the full backend, runtime, worker, migration-CLI, and ECR scan gates pass. No pip dependency or application API changed.

`.dockerignore` already excludes Git history, Terraform state/plans/tfvars/backend files, frontend, docs, quality results, caches, coverage, logs, and local artifacts. Docker history contains no credential, ignored configuration, or private-key material. Runtime remains non-root (`app`) with the existing uvicorn command and `/health` healthcheck.

## Verification before release build

- Ruff check/format, compileall: PASS
- Backend: 142 passed
- Overall coverage: 82.89%
- Critical-service coverage: 90.86%
- pip-audit: no known runtime dependency vulnerability
- Bandit and tracked-file secret scan: PASS
- Local `/health` and `/docs`: HTTP 200
- Worker runner and Alembic CLI startup: PASS; no migration applied

The intermediate Bookworm image was pushed as `d1f743a82c5c` with registry digest `sha256:ffd5c07ecf442b874ec483e1e4f861015e904f8b6759b87ff5402f48af1b8353`. Its completed ECR scan was CRITICAL 3, HIGH 5, MEDIUM 6, UNDEFINED 1, all CRITICAL/HIGH in inherited `perl-base 5.36.0-7+deb12u3`; `APP_SCAN_ACCEPTABLE = FAIL`, so no staging tfvars were changed. The Alpine candidate then repeated the full 142-test, 82.89% overall, 90.86% critical-service, pip-audit, Bandit, endpoint, worker, migration-CLI, non-root, layer-content, and secret gates before commit.

The final source commit, immutable image tag, registry digest, ECR scan counts, and remaining MEDIUM/LOW findings are recorded after the no-cache release build and registry scan.
