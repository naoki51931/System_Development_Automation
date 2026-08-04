import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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

MONEY = Numeric(18, 8)


class Estimate(TimestampMixin, Base):
    __tablename__ = "estimates"
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
    estimate_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="JPY")
    subtotal: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0")
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0")
    )
    total_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0")
    )
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "estimate_number",
            name="uq_estimates_organization_number",
        ),
        CheckConstraint(
            "status IN ('draft','calculating','internal_review','customer_review','approved','rejected','expired','superseded')",
            name="ck_estimates_status",
        ),
        CheckConstraint(
            "currency = upper(currency) AND length(currency) = 3",
            name="ck_estimates_currency",
        ),
        CheckConstraint(
            "subtotal >= 0 AND tax_amount >= 0 AND total_amount >= 0",
            name="ck_estimates_amounts",
        ),
        CheckConstraint(
            "total_amount = subtotal + tax_amount", name="ck_estimates_total"
        ),
        Index("ix_estimates_project_status", "project_id", "status"),
    )


class EstimateItem(Base):
    __tablename__ = "estimate_items"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    estimate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("estimates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    item_type: Mapped[str] = mapped_column(String(30), nullable=False)
    phase: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "item_type IN ('ai_runtime','artifact_value','human_review','cloud','maintenance','option','discount','tax')",
            name="ck_estimate_items_type",
        ),
        CheckConstraint(
            "source_type IN ('ai_run','artifact','manual','pricing_rule','cloud_estimate')",
            name="ck_estimate_items_source",
        ),
        CheckConstraint("quantity >= 0", name="ck_estimate_items_quantity"),
        CheckConstraint(
            "amount = round(quantity * unit_price, 8)",
            name="ck_estimate_items_calculated_amount",
        ),
        CheckConstraint(
            "(item_type = 'discount') OR (unit_price >= 0 AND amount >= 0)",
            name="ck_estimate_items_nonnegative",
        ),
        UniqueConstraint(
            "estimate_id", "display_order", name="uq_estimate_items_order"
        ),
        Index("ix_estimate_items_estimate", "estimate_id"),
    )


class PricingRule(TimestampMixin, Base):
    __tablename__ = "pricing_rules"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    base_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    complexity_multiplier: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("1")
    )
    quality_multiplier: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("1")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="JPY")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        CheckConstraint(
            "base_price >= 0 AND complexity_multiplier >= 0 AND quality_multiplier >= 0",
            name="ck_pricing_rules_values",
        ),
        Index(
            "ix_pricing_rules_resolution", "organization_id", "artifact_type", "enabled"
        ),
        Index(
            "uq_pricing_rules_system_type",
            "artifact_type",
            unique=True,
            postgresql_where=organization_id.is_(None),
        ),
        Index(
            "uq_pricing_rules_org_type",
            "organization_id",
            "artifact_type",
            unique=True,
            postgresql_where=organization_id.is_not(None),
        ),
    )


class ArtifactPricingSnapshot(Base):
    __tablename__ = "artifact_pricing_snapshots"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    estimate_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("estimate_items.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    pricing_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pricing_rules.id", ondelete="RESTRICT")
    )
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    base_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    complexity_multiplier: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    quality_multiplier: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    screen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    api_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    table_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    test_case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    calculated_value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "screen_count >= 0 AND api_count >= 0 AND table_count >= 0 AND test_case_count >= 0",
            name="ck_artifact_pricing_counts",
        ),
    )


class Contract(TimestampMixin, Base):
    __tablename__ = "contracts"
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
    estimate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("estimates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    contract_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    contract_type: Mapped[str] = mapped_column(String(30), nullable=False)
    customer_accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    customer_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    provider_accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    provider_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terms_version: Mapped[str] = mapped_column(String(50), nullable=False)
    document_artifact_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "contract_number",
            name="uq_contracts_organization_number",
        ),
        UniqueConstraint("estimate_id", name="uq_contracts_estimate"),
        CheckConstraint(
            "status IN ('draft','awaiting_customer','awaiting_provider','active','suspended','terminated','completed')",
            name="ck_contracts_status",
        ),
        CheckConstraint(
            "contract_type IN ('development','maintenance','additional_work')",
            name="ck_contracts_type",
        ),
        Index("ix_contracts_project_status", "project_id", "status"),
    )


class PaymentCustomer(TimestampMixin, Base):
    __tablename__ = "payment_customers"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_customer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_customer_id", name="uq_payment_customers_provider_id"
        ),
        UniqueConstraint(
            "organization_id", "provider", name="uq_payment_customers_org_provider"
        ),
    )


class PaymentMethod(TimestampMixin, Base):
    __tablename__ = "payment_methods"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    payment_customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_payment_method_id: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(30))
    last4: Mapped[str | None] = mapped_column(String(4))
    expiry_month: Mapped[int | None] = mapped_column(Integer)
    expiry_year: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_payment_method_id",
            name="uq_payment_methods_provider_id",
        ),
        CheckConstraint(
            "last4 IS NULL OR last4 ~ '^[0-9]{4}$'", name="ck_payment_methods_last4"
        ),
        CheckConstraint(
            "expiry_month IS NULL OR expiry_month BETWEEN 1 AND 12",
            name="ck_payment_methods_expiry_month",
        ),
    )


class PaymentIntent(TimestampMixin, Base):
    __tablename__ = "payment_intents"
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
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_payment_intent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_message_sanitized: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "idempotency_key",
            name="uq_payment_intents_idempotency",
        ),
        UniqueConstraint(
            "provider",
            "provider_payment_intent_id",
            name="uq_payment_intents_provider_id",
        ),
        CheckConstraint(
            "status IN ('requires_payment_method','requires_confirmation','processing','succeeded','failed','cancelled','refunded')",
            name="ck_payment_intents_status",
        ),
        CheckConstraint("amount >= 0", name="ck_payment_intents_amount"),
        Index("ix_payment_intents_contract_status", "contract_id", "status"),
    )


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"
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
    maintenance_contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_contracts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_subscription_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_subscription_id", name="uq_subscriptions_provider_id"
        ),
    )


class SubscriptionInvoice(TimestampMixin, Base):
    __tablename__ = "subscription_invoices"
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
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_invoice_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_due: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_event_id", name="uq_payment_events_provider_event"
        ),
        Index("ix_payment_events_status_received", "status", "received_at"),
    )


class MaintenancePlan(TimestampMixin, Base):
    __tablename__ = "maintenance_plans"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="JPY")
    monthly_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    included_ai_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    included_human_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    backup_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    support_response_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    monitoring_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    staging_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        Index(
            "uq_maintenance_plans_system_code",
            "code",
            unique=True,
            postgresql_where=organization_id.is_(None),
        ),
        Index(
            "uq_maintenance_plans_org_code",
            "organization_id",
            "code",
            unique=True,
            postgresql_where=organization_id.is_not(None),
        ),
    )


class MaintenanceContract(TimestampMixin, Base):
    __tablename__ = "maintenance_contracts"
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
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    maintenance_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    grace_period_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_subscription_id: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        UniqueConstraint("contract_id", name="uq_maintenance_contracts_contract"),
        CheckConstraint(
            "status IN ('pending','active','past_due','grace_period','suspended','deletion_scheduled','terminated')",
            name="ck_maintenance_contracts_status",
        ),
        Index("ix_maintenance_contracts_project_status", "project_id", "status"),
    )


class MaintenanceStatusEvent(Base):
    __tablename__ = "maintenance_status_events"
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
    maintenance_contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_contracts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        Index(
            "ix_maintenance_events_contract_effective",
            "maintenance_contract_id",
            "effective_at",
        ),
    )


class ResourceDeletionRequest(TimestampMixin, Base):
    __tablename__ = "resource_deletion_requests"
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
    maintenance_contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_contracts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_by_first: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_by_second: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_at_first: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at_second: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_reference: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','pending_first_approval','pending_second_approval','approved','cancelled','executed','failed')",
            name="ck_resource_deletion_requests_status",
        ),
        CheckConstraint(
            "approved_by_first IS NULL OR approved_by_second IS NULL OR approved_by_first <> approved_by_second",
            name="ck_resource_deletion_two_approvers",
        ),
        Index(
            "ix_deletion_requests_contract_status", "maintenance_contract_id", "status"
        ),
    )
