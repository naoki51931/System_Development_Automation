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

## Local AI, storage, review, and concurrency phase

AI settings resolve project -> organization -> safe system defaults. Billing uses Decimal/NUMERIC(18,8), rounds every non-zero partial minute up, and stores rate snapshots on each AI run. Artifact files use server-generated tenant keys and are verified by MIME type, size, and SHA-256 before immutable version registration. Review comments use audited state transitions, and SQLAlchemy version columns return conflicts instead of overwriting concurrent updates.

See `docs/ai_storage_workflow.md` for APIs, validation, mock automatic revision, retry escalation, and locking. This phase never calls OpenAI, Anthropic, AWS S3, RDS, Terraform, ECR, ECS, or a public environment. External provider and S3 classes are disabled stubs. API keys are never stored; future runtime credentials will come from AWS Secrets Manager.
