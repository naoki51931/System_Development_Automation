"""protect one active staging execution per organization and project

Revision ID: ef45ab67cd89
Revises: cd34ef56ab78
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "ef45ab67cd89"
down_revision: str | None = "cd34ef56ab78"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_deployment_executions_active_project_environment",
        "deployment_executions",
        ["organization_id", "project_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('requested','validating','authorized','prepared')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_deployment_executions_active_project_environment",
        table_name="deployment_executions",
    )
