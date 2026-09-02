import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeploymentPlan(Base):
    """Immutable identity and security metadata for a future staging apply."""

    __tablename__ = "deployment_plans"

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
    environment: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="created")
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    plan_storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    plan_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_size: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_format_version: Mapped[str] = mapped_column(
        String(30), nullable=False, default="terraform-show-json-v1"
    )
    terraform_root: Mapped[str] = mapped_column(String(1024), nullable=False)
    terraform_workspace: Mapped[str | None] = mapped_column(String(255))
    terraform_state_identity: Mapped[str | None] = mapped_column(String(1024))
    aws_account_id: Mapped[str | None] = mapped_column(String(32))
    aws_region: Mapped[str | None] = mapped_column(String(64))
    target_environment: Mapped[str] = mapped_column(String(30), nullable=False)
    plan_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    add_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    change_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    replace_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    destroy_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    security_gate_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="not_checked"
    )
    security_gate_result: Mapped[dict | None] = mapped_column(JSON)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    __table_args__ = (
        CheckConstraint(
            "environment = 'staging'", name="ck_deployment_plans_staging_only"
        ),
        CheckConstraint(
            "target_environment = 'staging'",
            name="ck_deployment_plans_target_staging_only",
        ),
        CheckConstraint(
            "status IN ('created','security_checked','approval_requested','approved','superseded','executed')",
            name="ck_deployment_plans_status",
        ),
        CheckConstraint(
            "security_gate_status IN ('not_checked','pass','review_required','blocked')",
            name="ck_deployment_plans_gate_status",
        ),
        CheckConstraint("plan_size >= 0", name="ck_deployment_plans_size"),
        Index(
            "ix_deployment_plans_project_environment",
            "organization_id",
            "project_id",
            "environment",
            "created_at",
        ),
        Index("ix_deployment_plans_checksum", "organization_id", "plan_sha256"),
    )
