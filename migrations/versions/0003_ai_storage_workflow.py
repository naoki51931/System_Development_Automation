"""AI settings, local artifact upload, review resolution, and optimistic locking.

Revision ID: 0003_ai_storage_workflow
Revises: 57d2abd856ae
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_ai_storage_workflow"
down_revision: str | None = "57d2abd856ae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "artifacts",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "reviews",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("ai_runs", sa.Column("billed_minutes", sa.Integer(), nullable=True))
    op.add_column(
        "ai_runs", sa.Column("minute_rate_snapshot", sa.Numeric(18, 8), nullable=True)
    )
    op.add_column(
        "ai_runs", sa.Column("input_rate_snapshot", sa.Numeric(18, 8), nullable=True)
    )
    op.add_column(
        "ai_runs", sa.Column("output_rate_snapshot", sa.Numeric(18, 8), nullable=True)
    )
    op.add_column(
        "ai_runs", sa.Column("calculated_cost", sa.Numeric(18, 8), nullable=True)
    )
    op.add_column(
        "ai_runs",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_ai_runs_billed_minutes",
        "ai_runs",
        "billed_minutes IS NULL OR billed_minutes >= 0",
    )
    op.create_check_constraint(
        "ck_ai_runs_calculated_cost",
        "ai_runs",
        "calculated_cost IS NULL OR calculated_cost >= 0",
    )

    op.create_table(
        "ai_settings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("operation_type", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("review_threshold", sa.Integer(), nullable=False),
        sa.Column("max_auto_revision_count", sa.Integer(), nullable=False),
        sa.Column("minute_rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("token_input_rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("token_output_rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="JPY"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "provider IN ('openai','anthropic')", name="ck_ai_settings_provider"
        ),
        sa.CheckConstraint(
            "operation_type IN ('hearing','estimate','document_generation','code_generation','review','revision','test_generation','deployment_analysis')",
            name="ck_ai_settings_operation",
        ),
        sa.CheckConstraint(
            "review_threshold BETWEEN 0 AND 100", name="ck_ai_settings_threshold"
        ),
        sa.CheckConstraint(
            "max_auto_revision_count BETWEEN 0 AND 10", name="ck_ai_settings_revisions"
        ),
        sa.CheckConstraint(
            "minute_rate >= 0 AND token_input_rate >= 0 AND token_output_rate >= 0",
            name="ck_ai_settings_rates",
        ),
        sa.CheckConstraint(
            "currency = upper(currency) AND length(currency) = 3",
            name="ck_ai_settings_currency",
        ),
    )
    op.create_index(
        "ix_ai_settings_resolution",
        "ai_settings",
        ["organization_id", "project_id", "provider", "model", "operation_type"],
    )
    op.create_index(
        "uq_ai_settings_project_scope",
        "ai_settings",
        ["organization_id", "project_id", "provider", "model", "operation_type"],
        unique=True,
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )
    op.create_index(
        "uq_ai_settings_organization_scope",
        "ai_settings",
        ["organization_id", "provider", "model", "operation_type"],
        unique=True,
        postgresql_where=sa.text("project_id IS NULL"),
    )

    op.create_table(
        "workflow_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(100), nullable=True),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "job_type IN ('auto_revision')", name="ck_workflow_jobs_type"
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','escalated','failed')",
            name="ck_workflow_jobs_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts BETWEEN 0 AND 10",
            name="ck_workflow_jobs_attempts",
        ),
    )
    op.create_index("ix_workflow_jobs_claim", "workflow_jobs", ["status", "locked_at"])
    op.create_index(
        "ix_workflow_jobs_project_created",
        "workflow_jobs",
        ["project_id", "created_at"],
    )

    op.create_table(
        "artifact_upload_intents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("artifact_id", sa.UUID(), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("mime_type", sa.String(255), nullable=False),
        sa.Column("expected_size", sa.Integer(), nullable=False),
        sa.Column("expected_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id"),
        sa.UniqueConstraint("storage_key"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("expected_size >= 0", name="ck_upload_intents_size"),
        sa.CheckConstraint(
            "status IN ('pending','completed','expired','cancelled')",
            name="ck_upload_intents_status",
        ),
    )
    op.create_index(
        "ix_upload_intents_artifact_status",
        "artifact_upload_intents",
        ["artifact_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_upload_intents_artifact_status", table_name="artifact_upload_intents"
    )
    op.drop_table("artifact_upload_intents")
    op.drop_index("ix_workflow_jobs_project_created", table_name="workflow_jobs")
    op.drop_index("ix_workflow_jobs_claim", table_name="workflow_jobs")
    op.drop_table("workflow_jobs")
    op.drop_index("uq_ai_settings_organization_scope", table_name="ai_settings")
    op.drop_index("uq_ai_settings_project_scope", table_name="ai_settings")
    op.drop_index("ix_ai_settings_resolution", table_name="ai_settings")
    op.drop_table("ai_settings")
    op.drop_constraint("ck_ai_runs_calculated_cost", "ai_runs", type_="check")
    op.drop_constraint("ck_ai_runs_billed_minutes", "ai_runs", type_="check")
    for column in (
        "version",
        "calculated_cost",
        "output_rate_snapshot",
        "input_rate_snapshot",
        "minute_rate_snapshot",
        "billed_minutes",
    ):
        op.drop_column("ai_runs", column)
    op.drop_column("reviews", "version")
    op.drop_column("artifacts", "version")
    op.drop_column("projects", "version")
