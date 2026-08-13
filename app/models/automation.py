import uuid
from datetime import datetime
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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.identity import TimestampMixin
from app.models.project import AI_OPERATIONS, AI_PROVIDERS, sql_values


class AISetting(TimestampMixin, Base):
    __tablename__ = "ai_settings"
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
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    review_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=95)
    max_auto_revision_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3
    )
    minute_rate: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    token_input_rate: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    token_output_rate: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="JPY")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        CheckConstraint(
            f"provider IN ({sql_values(AI_PROVIDERS)})", name="ck_ai_settings_provider"
        ),
        CheckConstraint(
            f"operation_type IN ({sql_values(AI_OPERATIONS)})",
            name="ck_ai_settings_operation",
        ),
        CheckConstraint(
            "review_threshold BETWEEN 0 AND 100", name="ck_ai_settings_threshold"
        ),
        CheckConstraint(
            "max_auto_revision_count BETWEEN 0 AND 10", name="ck_ai_settings_revisions"
        ),
        CheckConstraint(
            "minute_rate >= 0 AND token_input_rate >= 0 AND token_output_rate >= 0",
            name="ck_ai_settings_rates",
        ),
        CheckConstraint(
            "currency = upper(currency) AND length(currency) = 3",
            name="ck_ai_settings_currency",
        ),
        Index(
            "uq_ai_settings_project_scope",
            "organization_id",
            "project_id",
            "provider",
            "model",
            "operation_type",
            unique=True,
            postgresql_where=project_id.is_not(None),
        ),
        Index(
            "uq_ai_settings_organization_scope",
            "organization_id",
            "provider",
            "model",
            "operation_type",
            unique=True,
            postgresql_where=project_id.is_(None),
        ),
        Index(
            "ix_ai_settings_resolution",
            "organization_id",
            "project_id",
            "provider",
            "model",
            "operation_type",
        ),
    )


class WorkflowJob(TimestampMixin, Base):
    __tablename__ = "workflow_jobs"
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
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(100))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    resume_block_reason: Mapped[str | None] = mapped_column(String(255))
    resume_blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parent_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_jobs.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        CheckConstraint("job_type IN ('auto_revision')", name="ck_workflow_jobs_type"),
        CheckConstraint(
            "status IN ('pending','running','completed','escalated','failed')",
            name="ck_workflow_jobs_status",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND max_attempts BETWEEN 0 AND 10",
            name="ck_workflow_jobs_attempts",
        ),
        Index("ix_workflow_jobs_claim", "status", "locked_at"),
        Index("ix_workflow_jobs_project_created", "project_id", "created_at"),
    )


class WorkflowJobInput(Base):
    __tablename__ = "workflow_job_inputs"
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
    workflow_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_jobs.id", ondelete="RESTRICT"),
        unique=True,
    )
    document_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_generation_jobs.id", ondelete="RESTRICT"),
        unique=True,
    )
    input_type: Mapped[str] = mapped_column(String(30), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    source_reference_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_reference_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    access_context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    settings_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    template_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    input_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    input_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "(workflow_job_id IS NOT NULL)::int + (document_job_id IS NOT NULL)::int = 1",
            name="ck_workflow_job_inputs_one_job",
        ),
        CheckConstraint(
            "input_type IN ('document','ai_workflow')",
            name="ck_workflow_job_inputs_type",
        ),
        Index("ix_workflow_job_inputs_tenant", "organization_id", "project_id"),
    )


class WorkflowJobStep(Base):
    __tablename__ = "workflow_job_steps"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_input_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_job_inputs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    step_name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    idempotency_key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    result_reference: Mapped[str | None] = mapped_column(String(1024))
    result_hash: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "workflow_input_id", "step_name", name="uq_workflow_job_steps_name"
        ),
        CheckConstraint(
            "status IN ('pending','running','completed','failed')",
            name="ck_workflow_job_steps_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_workflow_job_steps_attempts"),
    )


class ArtifactUploadIntent(Base):
    __tablename__ = "artifact_upload_intents"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
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
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_size: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint("expected_size >= 0", name="ck_upload_intents_size"),
        CheckConstraint(
            "status IN ('pending','completed','expired','cancelled')",
            name="ck_upload_intents_status",
        ),
        Index("ix_upload_intents_artifact_status", "artifact_id", "status"),
    )
