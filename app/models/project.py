import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.identity import TimestampMixin

PROJECT_STATUSES = (
    "draft", "hearing", "estimating", "awaiting_payment", "requirements", "basic_design",
    "detailed_design", "development", "testing", "staging", "awaiting_acceptance",
    "production", "maintenance", "suspended", "closed",
)
PROJECT_PHASES = (
    "hearing", "estimate", "requirements", "basic_design", "detailed_design", "development",
    "testing", "staging", "acceptance", "production", "maintenance",
)
PROJECT_ROLES = ("project_owner", "project_manager", "reviewer", "developer", "customer", "viewer")
ARTIFACT_TYPES = (
    "hearing_sheet", "estimate", "requirements_definition", "basic_design", "detailed_design",
    "screen_design", "api_specification", "database_design", "test_specification", "test_report",
    "operation_manual", "release_procedure", "source_code",
)
ARTIFACT_STATUSES = (
    "draft", "ai_reviewing", "human_reviewing", "revision_requested", "approved", "superseded",
)
REVIEW_TYPES = ("ai", "human", "customer_acceptance", "security", "architecture", "code_quality", "test_quality")
REVIEW_STATUSES = ("pending", "in_progress", "passed", "failed", "changes_requested", "cancelled")
AI_PROVIDERS = ("openai", "anthropic")
AI_OPERATIONS = (
    "hearing", "estimate", "document_generation", "code_generation", "review", "revision",
    "test_generation", "deployment_analysis",
)


def sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    project_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    current_phase: Mapped[str] = mapped_column(String(30), nullable=False, default="hearing")
    customer_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    project_manager_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        UniqueConstraint("organization_id", "project_code", name="uq_projects_organization_code"),
        CheckConstraint(f"status IN ({sql_values(PROJECT_STATUSES)})", name="ck_projects_status"),
        CheckConstraint(f"current_phase IN ({sql_values(PROJECT_PHASES)})", name="ck_projects_phase"),
        Index("ix_projects_organization_status", "organization_id", "status"),
        Index("ix_projects_organization_updated", "organization_id", "updated_at"),
    )


class ProjectMember(Base):
    __tablename__ = "project_members"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_role: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        CheckConstraint(f"project_role IN ({sql_values(PROJECT_ROLES)})", name="ck_project_members_role"),
        CheckConstraint("status IN ('active', 'inactive')", name="ck_project_members_status"),
        Index("ix_project_members_user_status", "user_id", "status"),
    )


class AIRun(Base):
    __tablename__ = "ai_runs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    billed_minutes: Mapped[int | None] = mapped_column(Integer)
    minute_rate_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    input_rate_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    output_rate_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    calculated_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    request_hash: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message_sanitized: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint(f"provider IN ({sql_values(AI_PROVIDERS)})", name="ck_ai_runs_provider"),
        CheckConstraint(f"operation_type IN ({sql_values(AI_OPERATIONS)})", name="ck_ai_runs_operation"),
        CheckConstraint("retry_count >= 0", name="ck_ai_runs_retry_count"),
        CheckConstraint("estimated_cost IS NULL OR estimated_cost >= 0", name="ck_ai_runs_cost"),
        CheckConstraint("billed_minutes IS NULL OR billed_minutes >= 0", name="ck_ai_runs_billed_minutes"),
        CheckConstraint("calculated_cost IS NULL OR calculated_cost >= 0", name="ck_ai_runs_calculated_cost"),
        Index("ix_ai_runs_project_created", "project_id", "created_at"),
        Index("ix_ai_runs_organization_status", "organization_id", "status"),
    )


class Artifact(TimestampMixin, Base):
    __tablename__ = "artifacts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT", use_alter=True, name="fk_artifacts_current_version"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    versions: Mapped[list["ArtifactVersion"]] = relationship(back_populates="artifact", foreign_keys="ArtifactVersion.artifact_id")
    __table_args__ = (
        CheckConstraint(f"artifact_type IN ({sql_values(ARTIFACT_TYPES)})", name="ck_artifacts_type"),
        CheckConstraint(f"status IN ({sql_values(ARTIFACT_STATUSES)})", name="ck_artifacts_status"),
        Index("ix_artifacts_project_status", "project_id", "status"),
        Index("ix_artifacts_organization_type", "organization_id", "artifact_type"),
    )


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    artifact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="RESTRICT"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(20), nullable=False)
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_runs.id", ondelete="RESTRICT"))
    change_summary: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    artifact: Mapped[Artifact] = relationship(back_populates="versions", foreign_keys=[artifact_id])
    __table_args__ = (
        UniqueConstraint("artifact_id", "version_number", name="uq_artifact_versions_number"),
        CheckConstraint("version_number > 0", name="ck_artifact_versions_number"),
        CheckConstraint("file_size >= 0", name="ck_artifact_versions_file_size"),
        CheckConstraint("generated_by IN ('human', 'ai')", name="ck_artifact_versions_generated_by"),
        CheckConstraint("(generated_by = 'ai' AND ai_run_id IS NOT NULL) OR (generated_by = 'human' AND ai_run_id IS NULL)", name="ck_artifact_versions_ai_run"),
        Index("ix_artifact_versions_artifact_created", "artifact_id", "created_at"),
        Index("ix_artifact_versions_content_hash", "content_hash"),
    )


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    artifact_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT"), nullable=False)
    review_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_runs.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    score: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint(f"review_type IN ({sql_values(REVIEW_TYPES)})", name="ck_reviews_type"),
        CheckConstraint(f"status IN ({sql_values(REVIEW_STATUSES)})", name="ck_reviews_status"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_reviews_score"),
        CheckConstraint("(review_type = 'ai' AND ai_run_id IS NOT NULL AND reviewer_user_id IS NULL) OR (review_type <> 'ai' AND reviewer_user_id IS NOT NULL AND ai_run_id IS NULL)", name="ck_reviews_reviewer_source"),
        Index("ix_reviews_version_status", "artifact_version_id", "status"),
        Index("ix_reviews_project_created", "project_id", "created_at"),
    )


class ReviewComment(Base):
    __tablename__ = "review_comments"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="RESTRICT"), nullable=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    comment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    target_path: Mapped[str | None] = mapped_column(String(1024))
    target_line: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    __table_args__ = (
        CheckConstraint("length(trim(body)) > 0", name="ck_review_comments_body"),
        CheckConstraint("severity IN ('info', 'minor', 'major', 'critical')", name="ck_review_comments_severity"),
        CheckConstraint("status IN ('open', 'accepted', 'rejected', 'resolved')", name="ck_review_comments_status"),
        CheckConstraint("target_line IS NULL OR target_line > 0", name="ck_review_comments_target_line"),
        Index("ix_review_comments_review_status", "review_id", "status"),
    )


class ApprovalEvent(Base):
    __tablename__ = "approval_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    artifact_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT"), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("action IN ('submitted','approved','rejected','changes_requested','resubmitted','customer_accepted')", name="ck_approval_events_action"),
        Index("ix_approval_events_version_created", "artifact_version_id", "created_at"),
        Index("ix_approval_events_project_created", "project_id", "created_at"),
    )
