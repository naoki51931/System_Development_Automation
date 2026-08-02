import hashlib
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.audit import record_audit_log
from app.auth.dependencies import OrganizationAccess, ensure_resource_organization
from app.errors import AppError
from app.models.billing import (
    ArtifactPricingSnapshot,
    Contract,
    Estimate,
    EstimateItem,
    MaintenanceContract,
    MaintenancePlan,
    MaintenanceStatusEvent,
    PaymentEvent,
    PaymentIntent,
    PricingRule,
    ResourceDeletionRequest,
)
from app.models.project import AIRun, Artifact, Project
from app.services.payment_providers import PaymentProvider, PaymentProviderUnavailable

MONEY_QUANTUM = Decimal("0.00000001")
DEFAULT_TAX_RATE = Decimal("0.10000000")
DEFAULT_ARTIFACT_PRICES = {
    "hearing_sheet": Decimal("10000"),
    "estimate": Decimal("15000"),
    "requirements_definition": Decimal("100000"),
    "basic_design": Decimal("150000"),
    "detailed_design": Decimal("180000"),
    "screen_design": Decimal("30000"),
    "api_specification": Decimal("50000"),
    "database_design": Decimal("70000"),
    "test_specification": Decimal("60000"),
    "test_report": Decimal("40000"),
    "operation_manual": Decimal("50000"),
    "release_procedure": Decimal("40000"),
    "source_code": Decimal("200000"),
}
WRITE_ROLES = frozenset({"organization_owner", "organization_admin", "project_manager"})
CUSTOMER_ROLES = WRITE_ROLES | {"customer"}
PAYMENT_ROLES = WRITE_ROLES | {"customer"}
SECRET_PATTERN = re.compile(r"(?i)(card|cvc|api[_-]?key|token|secret|password)\s*[:=]\s*\S+")


def money(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal):
        raise AppError("INVALID_AMOUNT", "Amounts must use Decimal")
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def require_roles(access: OrganizationAccess, allowed: frozenset[str], code: str = "PAYMENT_ACTION_FORBIDDEN") -> None:
    if access.role_codes.isdisjoint(allowed):
        raise AppError(code, "Action is not permitted")


def check_version(resource, expected_version: int) -> None:
    if resource.version != expected_version:
        raise AppError("VERSION_CONFLICT", "Resource was updated by another request")


def safe_flush(session: Session) -> None:
    try:
        session.flush()
    except StaleDataError as exc:
        raise AppError("VERSION_CONFLICT", "Resource was updated by another request") from exc


def sanitize_failure(message: str | None) -> str | None:
    return SECRET_PATTERN.sub(r"\1=[REDACTED]", message)[:500] if message else None


def calculate_item_amount(item_type: str, quantity: Decimal, unit_price: Decimal) -> Decimal:
    if quantity < 0:
        raise AppError("INVALID_AMOUNT", "Quantity cannot be negative")
    if item_type == "discount":
        if unit_price > 0:
            raise AppError("INVALID_AMOUNT", "Discount unit price must be negative or zero")
    elif unit_price < 0:
        raise AppError("INVALID_AMOUNT", "Only discounts may be negative")
    return money(quantity * unit_price)


def calculate_tax(taxable_amount: Decimal, tax_rate: Decimal = DEFAULT_TAX_RATE) -> Decimal:
    if taxable_amount < 0 or tax_rate < 0:
        raise AppError("INVALID_AMOUNT", "Tax inputs cannot be negative")
    return money(taxable_amount * tax_rate)


def recalculate_estimate(session: Session, estimate: Estimate, tax_rate: Decimal = DEFAULT_TAX_RATE) -> Estimate:
    if estimate.status == "approved":
        raise AppError("INVALID_ESTIMATE_STATE", "Approved estimates are immutable")
    items = session.scalars(select(EstimateItem).where(EstimateItem.estimate_id == estimate.id)).all()
    subtotal = money(sum((item.amount for item in items if item.item_type != "tax"), Decimal("0")))
    if subtotal < 0:
        raise AppError("INVALID_AMOUNT", "Estimate subtotal cannot be negative")
    estimate.subtotal = subtotal
    estimate.tax_amount = calculate_tax(subtotal, tax_rate)
    estimate.total_amount = money(estimate.subtotal + estimate.tax_amount)
    return estimate


def add_estimate_item(
    session: Session,
    estimate: Estimate,
    *,
    item_type: str,
    description: str,
    quantity: Decimal,
    unit: str,
    unit_price: Decimal,
    source_type: str = "manual",
    source_reference_id: uuid.UUID | None = None,
    phase: str | None = None,
) -> EstimateItem:
    if estimate.status == "approved":
        raise AppError("INVALID_ESTIMATE_STATE", "Approved estimates are immutable")
    amount = calculate_item_amount(item_type, quantity, unit_price)
    order = (session.scalar(select(func.max(EstimateItem.display_order)).where(EstimateItem.estimate_id == estimate.id)) or 0) + 1
    item = EstimateItem(
        estimate_id=estimate.id, item_type=item_type, phase=phase, description=description,
        quantity=money(quantity), unit=unit, unit_price=money(unit_price), amount=amount,
        source_type=source_type, source_reference_id=source_reference_id, display_order=order,
    )
    session.add(item)
    session.flush()
    return item


def create_estimate(
    session: Session,
    project: Project,
    access: OrganizationAccess,
    *,
    estimate_number: str,
    valid_until: date,
    currency: str = "JPY",
    items: list[dict] | None = None,
    include_ai_runs: bool = True,
    include_artifacts: bool = True,
) -> Estimate:
    ensure_resource_organization(access, project.organization_id)
    require_roles(access, WRITE_ROLES)
    estimate = Estimate(
        organization_id=project.organization_id, project_id=project.id, estimate_number=estimate_number,
        status="draft", currency=currency, valid_until=valid_until, created_by_user_id=access.user.id,
    )
    session.add(estimate)
    session.flush()
    for values in items or []:
        add_estimate_item(session, estimate, **values)
    if include_ai_runs:
        generate_ai_run_items(session, estimate)
    if include_artifacts:
        generate_artifact_value_items(session, estimate)
    recalculate_estimate(session, estimate)
    session.flush()
    return estimate


def generate_ai_run_items(session: Session, estimate: Estimate) -> None:
    runs = session.scalars(select(AIRun).where(AIRun.organization_id == estimate.organization_id, AIRun.project_id == estimate.project_id, AIRun.status == "completed", AIRun.calculated_cost.is_not(None))).all()
    for run in runs:
        exists = session.scalar(select(EstimateItem.id).where(EstimateItem.estimate_id == estimate.id, EstimateItem.source_type == "ai_run", EstimateItem.source_reference_id == run.id))
        if exists is None:
            add_estimate_item(
                session, estimate, item_type="ai_runtime", description=f"AI runtime ({run.operation_type})",
                quantity=Decimal("1"), unit="run", unit_price=money(run.calculated_cost or Decimal("0")),
                source_type="ai_run", source_reference_id=run.id,
            )


def resolve_artifact_pricing(session: Session, organization_id: uuid.UUID, artifact_type: str) -> tuple[PricingRule | None, Decimal, Decimal, Decimal]:
    rule = session.scalar(select(PricingRule).where(PricingRule.organization_id == organization_id, PricingRule.artifact_type == artifact_type, PricingRule.enabled.is_(True)))
    if rule is None:
        rule = session.scalar(select(PricingRule).where(PricingRule.organization_id.is_(None), PricingRule.artifact_type == artifact_type, PricingRule.enabled.is_(True)))
    if rule:
        return rule, rule.base_price, rule.complexity_multiplier, rule.quality_multiplier
    return None, DEFAULT_ARTIFACT_PRICES.get(artifact_type, Decimal("0")), Decimal("1"), Decimal("1")


def calculate_artifact_value(base_price: Decimal, complexity: Decimal, quality: Decimal, *, screen_count: int = 0, api_count: int = 0, table_count: int = 0, test_case_count: int = 0) -> Decimal:
    if min(screen_count, api_count, table_count, test_case_count) < 0 or min(base_price, complexity, quality) < 0:
        raise AppError("INVALID_AMOUNT", "Artifact pricing inputs cannot be negative")
    size_factor = Decimal("1") + Decimal(screen_count) * Decimal("0.01") + Decimal(api_count) * Decimal("0.02") + Decimal(table_count) * Decimal("0.015") + Decimal(test_case_count) * Decimal("0.001")
    return money(base_price * complexity * quality * size_factor)


def generate_artifact_value_items(session: Session, estimate: Estimate) -> None:
    artifacts = session.scalars(select(Artifact).where(Artifact.organization_id == estimate.organization_id, Artifact.project_id == estimate.project_id)).all()
    for artifact in artifacts:
        exists = session.scalar(select(EstimateItem.id).where(EstimateItem.estimate_id == estimate.id, EstimateItem.source_type == "artifact", EstimateItem.source_reference_id == artifact.id))
        if exists is not None:
            continue
        rule, base, complexity, quality = resolve_artifact_pricing(session, estimate.organization_id, artifact.artifact_type)
        value = calculate_artifact_value(base, complexity, quality)
        item = add_estimate_item(
            session, estimate, item_type="artifact_value", description=f"Artifact value: {artifact.title}",
            quantity=Decimal("1"), unit="artifact", unit_price=value, source_type="artifact", source_reference_id=artifact.id,
        )
        session.add(ArtifactPricingSnapshot(
            estimate_item_id=item.id, artifact_id=artifact.id, pricing_rule_id=rule.id if rule else None,
            artifact_type=artifact.artifact_type, base_price=money(base), complexity_multiplier=money(complexity),
            quality_multiplier=money(quality), screen_count=0, api_count=0, table_count=0, test_case_count=0,
            calculated_value=value,
        ))


def transition_estimate(session: Session, estimate: Estimate, access: OrganizationAccess, action: str, expected_version: int) -> Estimate:
    ensure_resource_organization(access, estimate.organization_id)
    require_roles(access, WRITE_ROLES)
    check_version(estimate, expected_version)
    if estimate.status == "approved":
        raise AppError("INVALID_ESTIMATE_STATE", "Approved estimates are immutable")
    transitions = {("draft", "submit"): "customer_review", ("customer_review", "approve"): "approved", ("customer_review", "reject"): "rejected"}
    target = transitions.get((estimate.status, action))
    if target is None:
        raise AppError("INVALID_ESTIMATE_STATE", "Estimate state transition is not allowed")
    if target == "approved":
        if estimate.valid_until < datetime.now(timezone.utc).date():
            raise AppError("ESTIMATE_EXPIRED", "Estimate has expired")
        estimate.approved_by_user_id = access.user.id
        estimate.approved_at = datetime.now(timezone.utc)
    estimate.status = target
    safe_flush(session)
    project = session.get(Project, estimate.project_id)
    if project is not None and action in {"submit", "approve"}:
        from app.services.communications import emit_project_event
        emit_project_event(session, project, event_type="estimate_submitted" if action == "submit" else "estimate_approved", title=f"Estimate {action}", body=f"Estimate {estimate.estimate_number} was {action}ed.", severity="success" if action == "approve" else "info", action_url=f"/estimates/{estimate.id}", actor_user_id=access.user.id, aggregate_type="estimate", aggregate_id=estimate.id)
    return estimate


def create_contract(session: Session, estimate: Estimate, project: Project, access: OrganizationAccess, *, contract_number: str, contract_type: str, terms_version: str, document_artifact_version_id: uuid.UUID | None = None) -> Contract:
    ensure_resource_organization(access, estimate.organization_id)
    require_roles(access, WRITE_ROLES)
    if estimate.organization_id != project.organization_id or estimate.project_id != project.id:
        raise AppError("INVALID_CONTRACT_STATE", "Estimate and project scope do not match")
    if estimate.status != "approved":
        raise AppError("INVALID_ESTIMATE_STATE", "Only approved estimates can become contracts")
    if estimate.valid_until < datetime.now(timezone.utc).date():
        raise AppError("ESTIMATE_EXPIRED", "Estimate has expired")
    contract = Contract(
        organization_id=estimate.organization_id, project_id=estimate.project_id, estimate_id=estimate.id,
        contract_number=contract_number, status="draft", contract_type=contract_type,
        terms_version=terms_version, document_artifact_version_id=document_artifact_version_id,
    )
    session.add(contract)
    session.flush()
    return contract


def accept_contract(session: Session, contract: Contract, access: OrganizationAccess, *, party: str, expected_version: int, request_id: uuid.UUID) -> Contract:
    ensure_resource_organization(access, contract.organization_id)
    check_version(contract, expected_version)
    now = datetime.now(timezone.utc)
    before = contract.status
    if party == "customer":
        require_roles(access, CUSTOMER_ROLES)
        if contract.status not in {"draft", "awaiting_customer"} or contract.customer_accepted_at:
            raise AppError("INVALID_CONTRACT_STATE", "Customer acceptance is not allowed")
        contract.customer_accepted_by_user_id = access.user.id
        contract.customer_accepted_at = now
        contract.status = "active" if contract.provider_accepted_at else "awaiting_provider"
    elif party == "provider":
        require_roles(access, WRITE_ROLES)
        if contract.status not in {"draft", "awaiting_provider"} or contract.provider_accepted_at:
            raise AppError("INVALID_CONTRACT_STATE", "Provider acceptance is not allowed")
        contract.provider_accepted_by_user_id = access.user.id
        contract.provider_accepted_at = now
        contract.status = "active" if contract.customer_accepted_at else "awaiting_customer"
    else:
        raise AppError("INVALID_REQUEST", "Unknown contract party")
    if contract.status == "active":
        contract.started_at = now
    record_audit_log(
        session, organization_id=contract.organization_id, actor_user_id=access.user.id,
        action=f"contract.{party}_accepted", resource_type="contract", resource_id=contract.id,
        request_id=request_id, before={"status": before}, after={"status": contract.status, "terms_version": contract.terms_version},
    )
    safe_flush(session)
    if contract.status == "active":
        from app.services.communications import emit_project_event
        project = session.get(Project, contract.project_id)
        if project is not None:
            emit_project_event(session, project, event_type="contract_activated", title="Contract activated", body=f"Contract {contract.contract_number} is active.", severity="success", action_url=f"/contracts/{contract.id}", actor_user_id=access.user.id, aggregate_type="contract", aggregate_id=contract.id)
    return contract


def create_contract_payment_intent(session: Session, contract: Contract, access: OrganizationAccess, provider: PaymentProvider, *, idempotency_key: str, expected_amount: Decimal | None = None) -> PaymentIntent:
    ensure_resource_organization(access, contract.organization_id)
    require_roles(access, PAYMENT_ROLES)
    if contract.status != "active":
        raise AppError("CONTRACT_NOT_ACTIVE", "Contract is not active")
    estimate = session.get(Estimate, contract.estimate_id)
    if estimate is None or estimate.status != "approved":
        raise AppError("INVALID_CONTRACT_STATE", "Approved contract estimate is unavailable")
    if estimate.valid_until < datetime.now(timezone.utc).date():
        raise AppError("ESTIMATE_EXPIRED", "Estimate was expired when payment was initiated")
    if expected_amount is not None and money(expected_amount) != estimate.total_amount:
        raise AppError("AMOUNT_MISMATCH", "Requested amount does not match contract amount")
    existing_key = session.scalar(select(PaymentIntent).where(PaymentIntent.organization_id == contract.organization_id, PaymentIntent.provider == "mock", PaymentIntent.idempotency_key == idempotency_key))
    if existing_key:
        return existing_key
    duplicate = session.scalar(select(PaymentIntent.id).where(PaymentIntent.contract_id == contract.id, PaymentIntent.status.in_(["requires_payment_method", "requires_confirmation", "processing", "succeeded"])))
    if duplicate is not None:
        raise AppError("DUPLICATE_PAYMENT", "A payment already exists for this contract")
    try:
        external = provider.create_payment_intent(None, estimate.total_amount, estimate.currency, idempotency_key)
    except PaymentProviderUnavailable as exc:
        raise AppError("PAYMENT_PROVIDER_UNAVAILABLE", "Payment provider is unavailable") from exc
    intent = PaymentIntent(
        organization_id=contract.organization_id, project_id=contract.project_id, contract_id=contract.id,
        provider="mock", provider_payment_intent_id=external.id, status=external.status,
        currency=estimate.currency, amount=estimate.total_amount, idempotency_key=idempotency_key,
    )
    session.add(intent)
    session.flush()
    return intent


def confirm_contract_payment(session: Session, intent: PaymentIntent, contract: Contract, project: Project, access: OrganizationAccess, provider: PaymentProvider, expected_version: int) -> PaymentIntent:
    ensure_resource_organization(access, intent.organization_id)
    require_roles(access, PAYMENT_ROLES)
    check_version(intent, expected_version)
    if intent.contract_id != contract.id or intent.project_id != project.id or contract.organization_id != intent.organization_id:
        raise AppError("PAYMENT_ACTION_FORBIDDEN", "Payment scope does not match")
    if contract.status != "active":
        raise AppError("CONTRACT_NOT_ACTIVE", "Contract is not active")
    if intent.status == "succeeded":
        raise AppError("DUPLICATE_PAYMENT", "Payment already succeeded")
    if intent.status not in {"requires_confirmation", "failed", "processing"}:
        raise AppError("INVALID_STATE_TRANSITION", "Payment cannot be confirmed")
    try:
        result = provider.confirm_payment(intent.provider_payment_intent_id)
    except PaymentProviderUnavailable as exc:
        raise AppError("PAYMENT_PROVIDER_UNAVAILABLE", "Payment provider is unavailable") from exc
    intent.status = result.status
    intent.failure_code = result.failure_code
    intent.failure_message_sanitized = sanitize_failure(result.failure_message)
    if result.status == "succeeded":
        intent.confirmed_at = datetime.now(timezone.utc)
        project.status = "requirements"
        project.current_phase = "requirements"
    safe_flush(session)
    from app.services.communications import emit_project_event
    emit_project_event(session, project, event_type="payment_succeeded" if intent.status == "succeeded" else "payment_failed" if intent.status == "failed" else "payment_processing", title=f"Payment {intent.status}", body=f"Payment for contract {contract.contract_number} is {intent.status}.", severity="success" if intent.status == "succeeded" else "error" if intent.status == "failed" else "info", action_url=f"/payments/{intent.id}", actor_user_id=access.user.id, aggregate_type="payment_intent", aggregate_id=intent.id)
    return intent


def create_maintenance_contract(session: Session, project: Project, contract: Contract, plan: MaintenancePlan, access: OrganizationAccess, now: datetime) -> MaintenanceContract:
    ensure_resource_organization(access, project.organization_id)
    require_roles(access, WRITE_ROLES)
    if project.status not in {"production", "maintenance"}:
        raise AppError("INVALID_CONTRACT_STATE", "Project is not eligible for maintenance")
    if contract.organization_id != project.organization_id or contract.project_id != project.id or contract.status != "active":
        raise AppError("INVALID_CONTRACT_STATE", "Active maintenance contract scope is invalid")
    if contract.contract_type != "maintenance":
        raise AppError("INVALID_CONTRACT_STATE", "Contract is not a maintenance contract")
    if plan.organization_id not in {None, project.organization_id} or plan.status != "active":
        raise AppError("PAYMENT_ACTION_FORBIDDEN", "Maintenance plan is unavailable")
    maintenance = MaintenanceContract(
        organization_id=project.organization_id, project_id=project.id, contract_id=contract.id,
        maintenance_plan_id=plan.id, status="active", started_at=now,
        current_period_start=now, current_period_end=now + timedelta(days=30),
    )
    session.add(maintenance)
    session.flush()
    record_maintenance_event(session, maintenance, None, "active", "contract_started", now)
    return maintenance


def record_maintenance_event(session: Session, contract: MaintenanceContract, old: str | None, new: str, reason: str, now: datetime) -> None:
    session.add(MaintenanceStatusEvent(
        organization_id=contract.organization_id, project_id=contract.project_id,
        maintenance_contract_id=contract.id, from_status=old, to_status=new,
        reason_code=reason, effective_at=now,
    ))


def mark_maintenance_payment_failed(session: Session, contract: MaintenanceContract, now: datetime) -> MaintenanceContract:
    if contract.status not in {"active", "past_due"}:
        raise AppError("INVALID_STATE_TRANSITION", "Maintenance payment failure cannot be applied")
    old = contract.status
    contract.status = "past_due"
    if contract.grace_period_started_at is None:
        contract.grace_period_started_at = now
    record_maintenance_event(session, contract, old, "past_due", "payment_failed", now)
    project = session.get(Project, contract.project_id)
    if project is not None:
        from app.services.communications import emit_project_event
        emit_project_event(session, project, event_type="maintenance_past_due", title="Maintenance payment past due", body="Maintenance payment is past due.", severity="warning", action_url=f"/maintenance-contracts/{contract.id}", aggregate_type="maintenance_contract", aggregate_id=contract.id)
    return contract


def advance_maintenance_delinquency(session: Session, contract: MaintenanceContract, now: datetime) -> ResourceDeletionRequest | None:
    failed_at = contract.grace_period_started_at
    if failed_at is None or contract.status in {"active", "pending", "terminated"}:
        return None
    elapsed = now - failed_at
    if elapsed >= timedelta(days=7) and elapsed < timedelta(days=30):
        retried = session.scalar(select(MaintenanceStatusEvent.id).where(
            MaintenanceStatusEvent.maintenance_contract_id == contract.id,
            MaintenanceStatusEvent.reason_code == "invoice_retry_day_7",
        ))
        if retried is None:
            record_maintenance_event(session, contract, contract.status, contract.status, "invoice_retry_day_7", now)
    target = "deletion_scheduled" if elapsed >= timedelta(days=90) else "suspended" if elapsed >= timedelta(days=60) else "grace_period" if elapsed >= timedelta(days=30) else "past_due"
    order = {"past_due": 1, "grace_period": 2, "suspended": 3, "deletion_scheduled": 4}
    if order.get(target, 0) > order.get(contract.status, 0):
        old = contract.status
        contract.status = target
        if target == "grace_period":
            pass
        elif target == "suspended":
            contract.suspended_at = now
        elif target == "deletion_scheduled":
            contract.deletion_scheduled_at = now
        record_maintenance_event(session, contract, old, target, "delinquency_age", now)
        if target == "suspended":
            project = session.get(Project, contract.project_id)
            if project is not None:
                from app.services.communications import emit_project_event
                emit_project_event(session, project, event_type="maintenance_suspended", title="Maintenance suspended", body="Maintenance service is suspended.", severity="critical", action_url=f"/maintenance-contracts/{contract.id}", aggregate_type="maintenance_contract", aggregate_id=contract.id)
    if contract.status != "deletion_scheduled":
        return None
    existing = session.scalar(select(ResourceDeletionRequest).where(ResourceDeletionRequest.maintenance_contract_id == contract.id, ResourceDeletionRequest.status.notin_(["cancelled", "failed"])))
    if existing:
        return existing
    request = ResourceDeletionRequest(
        organization_id=contract.organization_id, project_id=contract.project_id,
        maintenance_contract_id=contract.id, status="pending_first_approval",
        reason="Maintenance payment overdue for 90 days", scheduled_for=now,
    )
    session.add(request)
    session.flush()
    return request


def recover_maintenance_payment(session: Session, contract: MaintenanceContract, now: datetime) -> MaintenanceContract:
    if contract.status not in {"past_due", "grace_period", "suspended", "deletion_scheduled"}:
        raise AppError("INVALID_STATE_TRANSITION", "Maintenance contract cannot be restored")
    old = contract.status
    contract.status = "active"
    contract.grace_period_started_at = None
    contract.suspended_at = None
    contract.deletion_scheduled_at = None
    requests = session.scalars(select(ResourceDeletionRequest).where(ResourceDeletionRequest.maintenance_contract_id == contract.id, ResourceDeletionRequest.status.in_(["draft", "pending_first_approval", "pending_second_approval", "approved"]))).all()
    for request in requests:
        request.status = "cancelled"
    record_maintenance_event(session, contract, old, "active", "payment_recovered", now)
    return contract


def approve_deletion_request(session: Session, request: ResourceDeletionRequest, access: OrganizationAccess, now: datetime, expected_version: int) -> ResourceDeletionRequest:
    ensure_resource_organization(access, request.organization_id)
    require_roles(access, WRITE_ROLES)
    check_version(request, expected_version)
    if request.status == "pending_first_approval":
        request.approved_by_first = access.user.id
        request.approved_at_first = now
        request.status = "pending_second_approval"
    elif request.status == "pending_second_approval":
        if request.approved_by_first == access.user.id:
            raise AppError("PAYMENT_ACTION_FORBIDDEN", "A second distinct approver is required")
        request.approved_by_second = access.user.id
        request.approved_at_second = now
        request.status = "approved"
    else:
        raise AppError("INVALID_STATE_TRANSITION", "Deletion request cannot be approved")
    record_audit_log(
        session, organization_id=request.organization_id, actor_user_id=access.user.id,
        action="resource_deletion_request.approved", resource_type="resource_deletion_request",
        resource_id=request.id, request_id=uuid.uuid4(), after={"status": request.status},
    )
    safe_flush(session)
    return request


def process_mock_webhook(session: Session, provider: PaymentProvider, organization_id: uuid.UUID, payload: bytes, signature: str) -> PaymentEvent:
    if not provider.verify_webhook(payload, signature):
        raise AppError("AUTHENTICATION_REQUIRED", "Webhook signature is invalid")
    payload_hash = hashlib.sha256(payload).hexdigest()
    try:
        data = json.loads(payload)
        event_id = str(data["id"])
        event_type = str(data["type"])
    except (ValueError, KeyError, TypeError) as exc:
        raise AppError("INVALID_REQUEST", "Webhook payload is invalid") from exc
    existing = session.scalar(select(PaymentEvent).where(PaymentEvent.provider == "mock", PaymentEvent.provider_event_id == event_id))
    if existing:
        raise AppError("WEBHOOK_ALREADY_PROCESSED", "Webhook event was already processed")
    now = datetime.now(timezone.utc)
    provider_intent_id = data.get("provider_payment_intent_id")
    event_status = {"payment_intent.succeeded": "succeeded", "payment_intent.failed": "failed", "payment_intent.processing": "processing"}.get(event_type)
    if provider_intent_id and event_status:
        intent = session.scalar(select(PaymentIntent).where(
            PaymentIntent.organization_id == organization_id,
            PaymentIntent.provider == "mock",
            PaymentIntent.provider_payment_intent_id == str(provider_intent_id),
        ))
        if intent is not None and intent.status != "succeeded":
            intent.status = event_status
            if event_status == "succeeded":
                intent.confirmed_at = now
                contract = session.get(Contract, intent.contract_id)
                project = session.get(Project, intent.project_id)
                if contract is not None and project is not None and contract.status == "active":
                    project.status = "requirements"
                    project.current_phase = "requirements"
    event = PaymentEvent(
        organization_id=organization_id, provider="mock", provider_event_id=event_id,
        event_type=event_type, status="processed", payload_hash=payload_hash,
        received_at=now, processed_at=now, retry_count=0,
    )
    session.add(event)
    session.flush()
    return event
