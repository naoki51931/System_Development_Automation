"""Add immutable workflow execution snapshots and resumable steps."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "8d4f2a7c9b11"
down_revision = "7c2f9a1e4d30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("workflow_jobs", "document_generation_jobs"):
        op.add_column(table, sa.Column("resume_block_reason", sa.String(255)))
        op.add_column(table, sa.Column("resume_blocked_at", sa.DateTime(timezone=True)))
        op.add_column(table, sa.Column("parent_job_id", postgresql.UUID(as_uuid=True)))
        op.add_column(table, sa.Column("idempotency_key", sa.String(64)))
        op.create_foreign_key(
            f"fk_{table}_parent_job",
            table,
            table,
            ["parent_job_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_unique_constraint(
            f"uq_{table}_idempotency_key", table, ["idempotency_key"]
        )

    op.create_table(
        "workflow_job_inputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("document_job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("input_type", sa.String(30), nullable=False),
        sa.Column("schema_version", sa.String(20), nullable=False),
        sa.Column("source_reference_type", sa.String(50), nullable=False),
        sa.Column("source_reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("access_context_hash", sa.String(64), nullable=False),
        sa.Column("settings_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("template_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("input_payload", postgresql.JSONB(), nullable=False),
        sa.Column("input_payload_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["workflow_job_id"], ["workflow_jobs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["document_job_id"], ["document_generation_jobs.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("workflow_job_id"),
        sa.UniqueConstraint("document_job_id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.CheckConstraint(
            "(workflow_job_id IS NOT NULL)::int + (document_job_id IS NOT NULL)::int = 1",
            name="ck_workflow_job_inputs_one_job",
        ),
        sa.CheckConstraint(
            "input_type IN ('document','ai_workflow')",
            name="ck_workflow_job_inputs_type",
        ),
    )
    op.create_index(
        "ix_workflow_job_inputs_tenant",
        "workflow_job_inputs",
        ["organization_id", "project_id"],
    )
    op.create_table(
        "workflow_job_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_input_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_name", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("result_reference", sa.String(1024)),
        sa.Column("result_hash", sa.String(64)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error_code", sa.String(100)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workflow_input_id"], ["workflow_job_inputs.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "workflow_input_id", "step_name", name="uq_workflow_job_steps_name"
        ),
        sa.UniqueConstraint("idempotency_key"),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed')",
            name="ck_workflow_job_steps_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_workflow_job_steps_attempts"),
    )
    op.execute(
        "CREATE FUNCTION prevent_workflow_snapshot_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'workflow snapshots and completed steps are immutable'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER workflow_job_inputs_immutable BEFORE UPDATE OR DELETE ON workflow_job_inputs FOR EACH ROW EXECUTE FUNCTION reject_immutable_change()".replace(
            "reject_immutable_change", "prevent_workflow_snapshot_mutation"
        )
    )
    op.execute(
        "CREATE TRIGGER workflow_job_steps_completed_immutable BEFORE UPDATE OR DELETE ON workflow_job_steps FOR EACH ROW WHEN (OLD.status = 'completed') EXECUTE FUNCTION reject_immutable_change()".replace(
            "reject_immutable_change", "prevent_workflow_snapshot_mutation"
        )
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER workflow_job_steps_completed_immutable ON workflow_job_steps"
    )
    op.execute("DROP TRIGGER workflow_job_inputs_immutable ON workflow_job_inputs")
    op.execute("DROP FUNCTION prevent_workflow_snapshot_mutation()")
    op.drop_table("workflow_job_steps")
    op.drop_index("ix_workflow_job_inputs_tenant", table_name="workflow_job_inputs")
    op.drop_table("workflow_job_inputs")
    for table in ("document_generation_jobs", "workflow_jobs"):
        op.drop_constraint(f"uq_{table}_idempotency_key", table, type_="unique")
        op.drop_constraint(f"fk_{table}_parent_job", table, type_="foreignkey")
        for column in (
            "idempotency_key",
            "parent_job_id",
            "resume_blocked_at",
            "resume_block_reason",
        ):
            op.drop_column(table, column)
