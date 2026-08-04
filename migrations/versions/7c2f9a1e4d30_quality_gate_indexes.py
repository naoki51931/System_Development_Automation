"""Add cursor and worker claim indexes for the staging quality gate."""

from alembic import op
import sqlalchemy as sa

revision = "7c2f9a1e4d30"
down_revision = "6b1e4c9f2a10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_audit_logs_org_cursor",
        "audit_logs",
        ["organization_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_notifications_org_cursor",
        "notifications",
        ["organization_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_chat_messages_room_cursor",
        "chat_messages",
        [
            "organization_id",
            "chat_room_id",
            sa.text("created_at DESC"),
            sa.text("id DESC"),
        ],
    )
    op.create_index(
        "ix_reviews_org_cursor",
        "reviews",
        ["organization_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_outbox_events_claim",
        "outbox_events",
        ["status", "available_at", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_claim", table_name="outbox_events")
    op.drop_index("ix_reviews_org_cursor", table_name="reviews")
    op.drop_index("ix_chat_messages_room_cursor", table_name="chat_messages")
    op.drop_index("ix_notifications_org_cursor", table_name="notifications")
    op.drop_index("ix_audit_logs_org_cursor", table_name="audit_logs")
