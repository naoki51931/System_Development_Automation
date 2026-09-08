"""safe staging terraform executor preparation records

Revision ID: cd34ef56ab78
Revises: ab12cd34ef56
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "cd34ef56ab78"
down_revision: str | None = "ab12cd34ef56"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deployment_executions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("deployment_plan_id", sa.UUID(), nullable=False),
        sa.Column("approval_id", sa.UUID(), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("plan_sha256", sa.String(64), nullable=False),
        sa.Column("expected_account_id", sa.String(32), nullable=False),
        sa.Column("expected_region", sa.String(64), nullable=False),
        sa.Column("expected_state_identity", sa.String(1024), nullable=False),
        sa.Column("expected_terraform_root", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(30), server_default="requested", nullable=False),
        sa.Column("authorization_result", sa.String(64)),
        sa.Column("authorization_reason", sa.String(128)),
        sa.Column("evidence", sa.JSON()),
        sa.Column("prepared_at", sa.DateTime(timezone=True)),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("correlation_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "status IN ('requested','validating','authorized','blocked','prepared','executed','failed')",
            name="ck_deployment_executions_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["deployment_plan_id"], ["deployment_plans.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["approval_id"], ["protected_approvals.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_deployment_executions_tenant",
        "deployment_executions",
        ["organization_id", "project_id", "requested_at"],
    )
    op.create_index(
        "uq_deployment_executions_active_plan",
        "deployment_executions",
        ["deployment_plan_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('requested','validating','authorized','prepared')"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_deployment_executions_tenant", table_name="deployment_executions")
    op.drop_index(
        "uq_deployment_executions_active_plan", table_name="deployment_executions"
    )
    op.drop_table("deployment_executions")
