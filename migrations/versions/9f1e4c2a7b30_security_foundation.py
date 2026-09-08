"""security foundation: protected approvals and enterprise audit fields

Revision ID: 9f1e4c2a7b30
Revises: 8d4f2a7c9b11
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "9f1e4c2a7b30"
down_revision: str | None = "8d4f2a7c9b11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column("actor_type", sa.String(20), nullable=False, server_default="human"),
    )
    op.add_column("audit_logs", sa.Column("approval_id", sa.UUID(), nullable=True))
    op.add_column("audit_logs", sa.Column("correlation_id", sa.UUID(), nullable=True))
    op.add_column("audit_logs", sa.Column("result", sa.String(30), nullable=True))
    op.add_column("audit_logs", sa.Column("reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_audit_logs_actor_type",
        "audit_logs",
        "actor_type IN ('human','system','ai_agent')",
    )
    op.alter_column("audit_logs", "actor_type", server_default=None)
    op.create_index(
        "ix_audit_logs_approval_id", "audit_logs", ["approval_id"], unique=False
    )
    op.create_index(
        "ix_audit_logs_correlation_id", "audit_logs", ["correlation_id"], unique=False
    )

    op.create_table(
        "protected_approvals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("requested_by_user_id", sa.UUID(), nullable=False),
        sa.Column("decided_by_user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=True),
        sa.Column("target_version", sa.Integer(), nullable=True),
        sa.Column("plan_checksum", sa.String(128), nullable=True),
        sa.Column("artifact_digest", sa.String(128), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="requested"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "requires_distinct_approver",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "action IN ('deployment.staging','deployment.production','terraform.plan','terraform.apply','secret.access','permission.change')",
            name="ck_protected_approvals_action",
        ),
        sa.CheckConstraint(
            "status IN ('requested','approved','rejected','expired','executed')",
            name="ck_protected_approvals_status",
        ),
        sa.CheckConstraint(
            "target_version IS NULL OR target_version > 0",
            name="ck_protected_approvals_target_version",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_protected_approvals_tenant_status",
        "protected_approvals",
        ["organization_id", "status", "requested_at"],
    )
    op.create_index(
        "ix_protected_approvals_resource",
        "protected_approvals",
        ["organization_id", "resource_type", "resource_id"],
    )
    op.create_foreign_key(
        "fk_audit_logs_approval_id",
        "audit_logs",
        "protected_approvals",
        ["approval_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_index("ix_protected_approvals_resource", table_name="protected_approvals")
    op.drop_index(
        "ix_protected_approvals_tenant_status", table_name="protected_approvals"
    )
    op.drop_constraint("fk_audit_logs_approval_id", "audit_logs", type_="foreignkey")
    op.drop_table("protected_approvals")
    op.drop_index("ix_audit_logs_correlation_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_approval_id", table_name="audit_logs")
    op.drop_constraint("ck_audit_logs_actor_type", "audit_logs", type_="check")
    for column in ("reason", "result", "correlation_id", "approval_id", "actor_type"):
        op.drop_column("audit_logs", column)
