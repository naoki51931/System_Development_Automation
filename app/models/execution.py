import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeploymentExecution(Base):
    """A non-executing authorization/preparation record for a staging plan."""

    __tablename__ = "deployment_executions"

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
    deployment_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deployment_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("protected_approvals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    plan_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_account_id: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_region: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_state_identity: Mapped[str] = mapped_column(String(1024), nullable=False)
    expected_terraform_root: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="requested")
    authorization_result: Mapped[str | None] = mapped_column(String(64))
    authorization_reason: Mapped[str | None] = mapped_column(String(128))
    evidence: Mapped[dict | None] = mapped_column(JSON)
    prepared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested','validating','authorized','blocked','prepared','executed','failed')",
            name="ck_deployment_executions_status",
        ),
        Index(
            "uq_deployment_executions_active_plan",
            "deployment_plan_id",
            unique=True,
            postgresql_where=text(
                "status IN ('requested','validating','authorized','prepared')"
            ),
        ),
        Index(
            "ix_deployment_executions_tenant",
            "organization_id",
            "project_id",
            "requested_at",
        ),
    )
