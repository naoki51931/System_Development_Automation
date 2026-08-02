# SystemNavigator AI

FastAPI application currently deployed on AWS ECS. The public `/`, `/health`, and `/docs` compatibility contracts remain unchanged while the design package is integrated incrementally.

## Local verification

Dependencies are pinned in `requirements.txt`. The identity integration tests require PostgreSQL and use only a local test database. Do not point test commands at RDS.

```bash
pytest -q
APP_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@LOCAL_HOST/LOCAL_DB alembic upgrade head --sql
```

Identity, Cognito access-token verification, organization membership RBAC, migration behavior, and RDS preflight requirements are documented in `docs/identity_access.md`.

Terraform apply/destroy, AWS resource changes, ECR pushes, ECS deployments, RDS connections, and RDS migrations require explicit review and approval.
