# SystemNavigator AI

FastAPI application currently deployed on AWS ECS. The public `/`, `/health`, and `/docs` compatibility contracts remain unchanged while the design package is integrated incrementally.

## Local verification

Dependencies are pinned in `requirements.txt`. The identity integration tests require PostgreSQL and use only a local test database. Do not point test commands at RDS.

```bash
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@LOCAL_HOST/LOCAL_DB pytest -q
APP_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@LOCAL_HOST/LOCAL_DB alembic upgrade head --sql
```

Identity and Cognito tenant boundaries are documented in `docs/identity_access.md`. Project, artifact, immutable version, AI/human review, approval workflow, additive migration, and RDS preflight requirements are documented in `docs/project_artifact_review.md`. The minimal API contract is in `schemas/openapi.yaml`.

The project workflow is `draft -> ai_reviewing -> human_reviewing -> approved`, with change requests creating a new immutable artifact version. All tenant resources are checked against authenticated organization membership; request organization IDs are never trusted alone.

Terraform apply/destroy, AWS resource changes, ECR pushes, ECS deployments, RDS connections, and RDS migrations require explicit review and approval.
