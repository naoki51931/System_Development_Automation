"""staging deployment plan and security gate metadata

Revision ID: ab12cd34ef56
Revises: 9f1e4c2a7b30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "ab12cd34ef56"
down_revision: str | None = "9f1e4c2a7b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deployment_plans",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("environment", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="created"),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("plan_storage_key", sa.String(1024), nullable=False),
        sa.Column("plan_sha256", sa.String(64), nullable=False),
        sa.Column("plan_size", sa.Integer(), nullable=False),
        sa.Column(
            "plan_format_version",
            sa.String(30),
            nullable=False,
            server_default="terraform-show-json-v1",
        ),
        sa.Column("terraform_root", sa.String(1024), nullable=False),
        sa.Column("terraform_workspace", sa.String(255), nullable=True),
        sa.Column("terraform_state_identity", sa.String(1024), nullable=True),
        sa.Column("aws_account_id", sa.String(32), nullable=True),
        sa.Column("aws_region", sa.String(64), nullable=True),
        sa.Column("target_environment", sa.String(30), nullable=False),
        sa.Column("plan_summary", sa.JSON(), nullable=False),
        sa.Column("add_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("change_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("replace_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("destroy_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "security_gate_status",
            sa.String(30),
            nullable=False,
            server_default="not_checked",
        ),
        sa.Column("security_gate_result", sa.JSON(), nullable=True),
        sa.Column("approval_id", sa.UUID(), nullable=True),
        sa.Column("superseded_by_id", sa.UUID(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_by_user_id", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "environment = 'staging'", name="ck_deployment_plans_staging_only"
        ),
        sa.CheckConstraint(
            "target_environment = 'staging'",
            name="ck_deployment_plans_target_staging_only",
        ),
        sa.CheckConstraint(
            "status IN ('created','security_checked','approval_requested','approved','superseded','executed')",
            name="ck_deployment_plans_status",
        ),
        sa.CheckConstraint(
            "security_gate_status IN ('not_checked','pass','review_required','blocked')",
            name="ck_deployment_plans_gate_status",
        ),
        sa.CheckConstraint("plan_size >= 0", name="ck_deployment_plans_size"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["executed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_deployment_plans_project_environment",
        "deployment_plans",
        ["organization_id", "project_id", "environment", "created_at"],
    )
    op.create_index(
        "ix_deployment_plans_checksum",
        "deployment_plans",
        ["organization_id", "plan_sha256"],
    )


def downgrade() -> None:
    op.drop_index("ix_deployment_plans_checksum", table_name="deployment_plans")
    op.drop_index(
        "ix_deployment_plans_project_environment", table_name="deployment_plans"
    )
    op.drop_table("deployment_plans")
