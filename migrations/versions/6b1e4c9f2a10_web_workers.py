"""web portal and outbox worker lease metadata
Revision ID: 6b1e4c9f2a10
Revises: d8685773bc4a
"""
from alembic import op
import sqlalchemy as sa
revision="6b1e4c9f2a10"; down_revision="d8685773bc4a"; branch_labels=None; depends_on=None

def upgrade():
    op.add_column("outbox_events", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"))
    for name, typ in [("locked_at",sa.DateTime(timezone=True)),("locked_by",sa.String(100)),("lease_expires_at",sa.DateTime(timezone=True)),("heartbeat_at",sa.DateTime(timezone=True)),("last_error_code",sa.String(100)),("dead_lettered_at",sa.DateTime(timezone=True))]: op.add_column("outbox_events",sa.Column(name,typ))
    op.drop_constraint("ck_outbox_events_status","outbox_events",type_="check")
    op.create_check_constraint("ck_outbox_events_status","outbox_events","status IN ('pending','processed','failed','queued','processing','completed','retry_wait','dead_letter')")
    op.create_index("ix_outbox_events_lease","outbox_events",["status","available_at","lease_expires_at"])

def downgrade():
    op.drop_index("ix_outbox_events_lease",table_name="outbox_events")
    op.drop_constraint("ck_outbox_events_status","outbox_events",type_="check")
    op.create_check_constraint("ck_outbox_events_status","outbox_events","status IN ('pending','processing','processed','failed')")
    for name in ["dead_lettered_at","last_error_code","heartbeat_at","lease_expires_at","locked_by","locked_at","max_attempts"]: op.drop_column("outbox_events",name)
