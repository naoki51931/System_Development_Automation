import uuid
from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.identity import TimestampMixin


class NotificationPreference(TimestampMixin, Base):
    __tablename__ = "notification_preferences"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    digest_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="immediate"
    )
    quiet_hours_start: Mapped[time | None] = mapped_column()
    quiet_hours_end: Mapped[time | None] = mapped_column()
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, default="UTC")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            "event_type",
            name="uq_notification_preferences_scope",
        ),
        CheckConstraint(
            "digest_mode IN ('immediate','hourly','daily','none')",
            name="ck_notification_preferences_digest",
        ),
        Index("ix_notification_preferences_user", "organization_id", "user_id"),
    )


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT")
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    action_url: Mapped[str | None] = mapped_column(String(1024))
    deduplication_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            "deduplication_key",
            name="uq_notifications_deduplication",
        ),
        CheckConstraint(
            "severity IN ('info','success','warning','error','critical')",
            name="ck_notifications_severity",
        ),
        CheckConstraint(
            "status IN ('pending','delivered','read','dismissed','expired')",
            name="ck_notifications_status",
        ),
        CheckConstraint(
            "action_url IS NULL OR (action_url LIKE '/%' AND action_url NOT LIKE '//%')",
            name="ck_notifications_internal_url",
        ),
        Index(
            "ix_notifications_user_status_created",
            "organization_id",
            "user_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_notifications_org_cursor",
            "organization_id",
            created_at.desc(),
            id.desc(),
        ),
    )


class NotificationDelivery(TimestampMixin, Base):
    __tablename__ = "notification_deliveries"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notifications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_message_sanitized: Mapped[str | None] = mapped_column(Text)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    __table_args__ = (
        CheckConstraint(
            "channel IN ('in_app','email')", name="ck_notification_deliveries_channel"
        ),
        CheckConstraint(
            "status IN ('pending','scheduled','sending','sent','delivered','failed','cancelled')",
            name="ck_notification_deliveries_status",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND max_attempts BETWEEN 1 AND 10",
            name="ck_notification_deliveries_attempts",
        ),
        UniqueConstraint(
            "notification_id", "channel", name="uq_notification_deliveries_channel"
        ),
        Index("ix_notification_deliveries_schedule", "status", "scheduled_at"),
    )


class EmailTemplate(TimestampMixin, Base):
    __tablename__ = "email_templates"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    template_code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_template: Mapped[str] = mapped_column(String(500), nullable=False)
    body_text_template: Mapped[str] = mapped_column(Text, nullable=False)
    body_html_template: Mapped[str | None] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(String(20), nullable=False, default="ja")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','approved','retired')", name="ck_email_templates_status"
        ),
        Index(
            "uq_email_templates_system_version",
            "template_code",
            "locale",
            "version_number",
            unique=True,
            postgresql_where=organization_id.is_(None),
        ),
        Index(
            "uq_email_templates_org_version",
            "organization_id",
            "template_code",
            "locale",
            "version_number",
            unique=True,
            postgresql_where=organization_id.is_not(None),
        ),
        Index(
            "ix_email_templates_resolution",
            "organization_id",
            "template_code",
            "locale",
            "status",
            "version_number",
        ),
    )


class EmailMessage(TimestampMixin, Base):
    __tablename__ = "email_messages"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT")
    )
    notification_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notifications.id", ondelete="RESTRICT")
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("email_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recipient_email_snapshot: Mapped[str] = mapped_column(String(320), nullable=False)
    subject_snapshot: Mapped[str] = mapped_column(String(500), nullable=False)
    body_text_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    body_html_snapshot: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_message_sanitized: Mapped[str | None] = mapped_column(Text)
    deduplication_key: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "deduplication_key",
            name="uq_email_messages_deduplication",
        ),
        CheckConstraint(
            "status IN ('draft','queued','sending','sent','delivered','failed','cancelled')",
            name="ck_email_messages_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_email_messages_attempts"),
        Index("ix_email_messages_schedule", "status", "scheduled_at"),
    )


class DocumentTemplate(TimestampMixin, Base):
    __tablename__ = "document_templates"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    template_code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    locale: Mapped[str] = mapped_column(String(20), nullable=False, default="ja")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    template_storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    __table_args__ = (
        CheckConstraint(
            "format IN ('html','docx','xlsx','markdown')",
            name="ck_document_templates_format",
        ),
        CheckConstraint(
            "status IN ('draft','approved','retired')",
            name="ck_document_templates_status",
        ),
        Index(
            "uq_document_templates_system_version",
            "template_code",
            "locale",
            "version_number",
            unique=True,
            postgresql_where=organization_id.is_(None),
        ),
        Index(
            "uq_document_templates_org_version",
            "organization_id",
            "template_code",
            "locale",
            "version_number",
            unique=True,
            postgresql_where=organization_id.is_not(None),
        ),
        Index(
            "ix_document_templates_resolution",
            "organization_id",
            "document_type",
            "locale",
            "status",
            "version_number",
        ),
    )


class DocumentGenerationJob(TimestampMixin, Base):
    __tablename__ = "document_generation_jobs"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_templates.id", ondelete="RESTRICT")
    )
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="RESTRICT")
    )
    artifact_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    output_format: Mapped[str] = mapped_column(String(20), nullable=False)
    input_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(1024))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    file_size: Mapped[int | None] = mapped_column(Integer)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_message_sanitized: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "project_id",
            "document_type",
            "template_id",
            "output_format",
            "input_payload_hash",
            name="uq_document_jobs_idempotency",
        ),
        CheckConstraint(
            "status IN ('queued','processing','completed','failed','cancelled')",
            name="ck_document_jobs_status",
        ),
        CheckConstraint(
            "output_format IN ('pdf','docx','xlsx','html','markdown')",
            name="ck_document_jobs_output",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND max_attempts BETWEEN 1 AND 10",
            name="ck_document_jobs_attempts",
        ),
        Index("ix_document_jobs_project_status", "project_id", "status"),
    )


class ChatRoom(TimestampMixin, Base):
    __tablename__ = "chat_rooms"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    room_type: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        CheckConstraint(
            "room_type IN ('project','support','review','maintenance')",
            name="ck_chat_rooms_type",
        ),
        CheckConstraint(
            "status IN ('active','archived','closed')", name="ck_chat_rooms_status"
        ),
        Index("ix_chat_rooms_project_status", "project_id", "status"),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    chat_room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_rooms.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sender_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    message_type: Mapped[str] = mapped_column(String(30), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    reply_to_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        CheckConstraint(
            "message_type IN ('user','system','ai','review','change_request')",
            name="ck_chat_messages_type",
        ),
        CheckConstraint(
            "status IN ('active','edited','deleted','moderated')",
            name="ck_chat_messages_status",
        ),
        CheckConstraint(
            "length(trim(body)) BETWEEN 1 AND 10000", name="ck_chat_messages_body"
        ),
        CheckConstraint(
            "(message_type IN ('system','ai') AND sender_user_id IS NULL) OR (message_type NOT IN ('system','ai') AND sender_user_id IS NOT NULL)",
            name="ck_chat_messages_sender",
        ),
        Index("ix_chat_messages_room_created", "chat_room_id", "created_at"),
        Index(
            "ix_chat_messages_room_cursor",
            "organization_id",
            "chat_room_id",
            created_at.desc(),
            id.desc(),
        ),
    )


class ChatAttachment(Base):
    __tablename__ = "chat_attachments"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    chat_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="RESTRICT"),
        nullable=False,
    )
    artifact_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint(
            "chat_message_id", "artifact_version_id", name="uq_chat_attachments_version"
        ),
        CheckConstraint("file_size >= 0", name="ck_chat_attachments_size"),
    )


class ChangeRequest(TimestampMixin, Base):
    __tablename__ = "change_requests"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    chat_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    scope_type: Mapped[str] = mapped_column(String(30), nullable=False)
    estimate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimates.id", ondelete="RESTRICT")
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','analyzing','awaiting_customer_approval','approved','rejected','in_progress','completed','cancelled')",
            name="ck_change_requests_status",
        ),
        CheckConstraint(
            "priority IN ('low','normal','high','urgent')",
            name="ck_change_requests_priority",
        ),
        CheckConstraint(
            "scope_type IN ('question','bug','minor_change','major_change','new_feature','infrastructure')",
            name="ck_change_requests_scope",
        ),
        Index("ix_change_requests_project_status", "project_id", "status"),
    )


class ChangeRequestImpact(Base):
    __tablename__ = "change_request_impacts"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    change_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("change_requests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    impact_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_reference: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "impact_type IN ('screen','api','database','document','test','infrastructure','schedule','cost')",
            name="ck_change_request_impacts_type",
        ),
        CheckConstraint(
            "estimated_minutes >= 0 AND estimated_amount >= 0",
            name="ck_change_request_impacts_values",
        ),
        Index("ix_change_request_impacts_request", "change_request_id"),
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(100))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "event_type",
            "aggregate_type",
            "aggregate_id",
            "payload_hash",
            name="uq_outbox_events_deduplication",
        ),
        CheckConstraint(
            "status IN ('pending','processed','failed','queued','processing','completed','retry_wait','dead_letter')",
            name="ck_outbox_events_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_outbox_events_attempts"),
        Index("ix_outbox_events_available", "status", "available_at"),
        Index("ix_outbox_events_claim", "status", "available_at", "created_at", "id"),
    )
