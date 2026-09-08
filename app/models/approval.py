import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProtectedApproval(Base):
    """An approval record for a future protected action; it never executes it."""

    __tablename__ = "protected_approvals"
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
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    target_version: Mapped[int | None] = mapped_column(Integer)
    plan_checksum: Mapped[str | None] = mapped_column(String(128))
    artifact_digest: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested")
    reason: Mapped[str | None] = mapped_column(Text)
    requires_distinct_approver: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "action IN ('deployment.staging','deployment.production','terraform.plan','terraform.apply','secret.access','permission.change')",
            name="ck_protected_approvals_action",
        ),
        CheckConstraint(
            "status IN ('requested','approved','rejected','expired','executed')",
            name="ck_protected_approvals_status",
        ),
        CheckConstraint(
            "target_version IS NULL OR target_version > 0",
            name="ck_protected_approvals_target_version",
        ),
        Index(
            "ix_protected_approvals_tenant_status",
            "organization_id",
            "status",
            "requested_at",
        ),
        Index(
            "ix_protected_approvals_resource",
            "organization_id",
            "resource_type",
            "resource_id",
        ),
    )
