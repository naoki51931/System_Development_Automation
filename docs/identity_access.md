# Identity, tenant, and access-control design

## Identity and organization membership

`users` is global. `email` and Cognito `sub` are globally unique, and email is normalized to lowercase. A user can join multiple organizations through `organization_memberships`. Roles are assigned to each membership through `membership_roles`, so the same user can be an administrator in one organization and a reviewer in another.

```text
users 1 ── N organization_memberships N ── 1 organizations
                         │
                         1
                         │
                         N membership_roles N ── 1 roles
```

Organization deletion is restricted while memberships or audit logs exist. User deletion is restricted while memberships exist; users are normally disabled by changing `status`. Deleting a membership cascades only to its membership-role assignments. Audit-log actor references become null if an otherwise-unreferenced user is deleted.

## Cognito authentication

API authorization uses Cognito access tokens, not ID tokens. `CognitoAccessTokenVerifier` verifies the RS256 signature with an injected key provider and validates issuer, expiration, subject, `token_use=access`, and `client_id` or audience. JWK retrieval and caching will be wired when Cognito infrastructure is approved. Tests inject a static verifier or local RSA public key and never contact AWS.

Authorization order:

```text
JWT validation
→ users.cognito_sub lookup and active-status check
→ active organization_memberships check
→ membership_roles check
→ resource organization_id check
→ operation
```

Client-provided organization identifiers never establish access by themselves.

## Audit safety

`audit_logs` is append-only. PostgreSQL rejects updates and deletes through a trigger. Application payload sanitization recursively redacts passwords, tokens, API keys, authorization values, and client secrets. Audit records must not contain raw secrets.

## Migration and seed

Migration `0002_identity_access` only creates new tables, constraints, indexes, and the append-only trigger. It does not rename, delete, or alter existing application tables. System roles are inserted separately and idempotently with:

```bash
APP_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DB python -m app.seed
```

No role uses a fixed UUID.

## Before any RDS application

- Confirm the target AWS account, region, RDS identifier, database name, and backup/PITR status.
- Take and verify a restorable snapshot according to the approved change procedure.
- Inspect current tables and Alembic version; confirm none of the six new table names already exist.
- Review the exact offline SQL and confirm it contains no `DROP`, `ALTER` of existing tables, or destructive operation.
- Confirm the ECS task role can read only the approved database secret; never place credentials in source, task plaintext, logs, or plans.
- Confirm a least-privilege migration principal and application principal, maintenance window, lock timeout, monitoring, and rollback procedure.
- Run the migration first against a production-like restored copy or staging database.
- Obtain explicit approval before RDS connection or migration execution.
