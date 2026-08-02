import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, require_organization_access
from app.errors import AppError
from app.models import MembershipRole, Organization, OrganizationMembership, Role, User
from app.models.billing import (
    Contract,
    Estimate,
    MaintenanceContract,
    MaintenancePlan,
    PaymentEvent,
    PaymentMethod,
    ResourceDeletionRequest,
)
from app.models.project import Project
from app.services.billing import (
    accept_contract,
    add_estimate_item,
    advance_maintenance_delinquency,
    approve_deletion_request,
    calculate_artifact_value,
    calculate_item_amount,
    calculate_tax,
    create_contract,
    create_contract_payment_intent,
    create_estimate,
    create_maintenance_contract,
    confirm_contract_payment,
    mark_maintenance_payment_failed,
    process_mock_webhook,
    recalculate_estimate,
    recover_maintenance_payment,
    transition_estimate,
)
from app.services.payment_providers import MockPaymentProvider, PaymentProviderUnavailable, StripePaymentProviderStub
from app.services.workflow import create_project


def context(session: Session, suffix: str = "billing"):
    organization = Organization(name=f"Org {suffix}", status="active")
    user = User(cognito_sub=f"sub-{suffix}-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com", display_name=suffix, status="active")
    role = Role(code=f"bill-{uuid.uuid4().hex[:20]}", display_name="Billing Admin", is_system=False)
    membership = OrganizationMembership(organization=organization, user=user, status="active")
    membership.roles.append(MembershipRole(role=role))
    session.add(membership)
    session.flush()
    raw = require_organization_access(organization.id, AuthenticatedUser(user), session)
    access = type(raw)(raw.user, raw.membership, frozenset({"organization_admin", "customer"}))
    project = create_project(session, access, project_code=f"P-{uuid.uuid4().hex[:12]}", name="Billing Project", status="draft", current_phase="estimate")
    return organization, user, access, project


def estimate_fixture(session: Session, suffix: str = "estimate", valid_until: date | None = None):
    organization, user, access, project = context(session, suffix)
    estimate = create_estimate(
        session, project, access, estimate_number=f"E-{uuid.uuid4().hex[:12]}",
        valid_until=valid_until or date.today() + timedelta(days=30), include_ai_runs=False, include_artifacts=False,
        items=[
            {"item_type": "option", "description": "Development", "quantity": Decimal("2.00000000"), "unit": "day", "unit_price": Decimal("100.12345678")},
            {"item_type": "discount", "description": "Discount", "quantity": Decimal("1.00000000"), "unit": "lot", "unit_price": Decimal("-10.00000000")},
        ],
    )
    return organization, user, access, project, estimate


def active_contract_fixture(session: Session, suffix: str = "contract", contract_type: str = "development"):
    organization, user, access, project, estimate = estimate_fixture(session, suffix)
    transition_estimate(session, estimate, access, "submit", estimate.version)
    transition_estimate(session, estimate, access, "approve", estimate.version)
    contract = create_contract(
        session, estimate, project, access, contract_number=f"C-{uuid.uuid4().hex[:12]}",
        contract_type=contract_type, terms_version="terms-v1",
    )
    accept_contract(session, contract, access, party="customer", expected_version=contract.version, request_id=uuid.uuid4())
    accept_contract(session, contract, access, party="provider", expected_version=contract.version, request_id=uuid.uuid4())
    return organization, user, access, project, estimate, contract


def test_estimate_recalculates_decimal_tax_and_discount(db_session: Session):
    _org, _user, _access, _project, estimate = estimate_fixture(db_session)
    assert estimate.subtotal == Decimal("190.24691356")
    assert estimate.tax_amount == Decimal("19.02469136")
    assert estimate.total_amount == Decimal("209.27160492")
    assert calculate_tax(Decimal("0.00000005")) == Decimal("0.00000001")


@pytest.mark.parametrize(
    ("item_type", "quantity", "price"),
    [("option", Decimal("1"), Decimal("-1")), ("discount", Decimal("1"), Decimal("1")), ("option", Decimal("-1"), Decimal("1"))],
)
def test_estimate_rejects_invalid_negative_values(item_type: str, quantity: Decimal, price: Decimal):
    with pytest.raises(AppError) as error:
        calculate_item_amount(item_type, quantity, price)
    assert error.value.code == "INVALID_AMOUNT"


def test_estimate_number_unique_in_organization(db_session: Session):
    organization, user, _access, project, estimate = estimate_fixture(db_session)
    db_session.add(Estimate(
        organization_id=organization.id, project_id=project.id, estimate_number=estimate.estimate_number,
        status="draft", currency="JPY", subtotal=Decimal("0"), tax_amount=Decimal("0"), total_amount=Decimal("0"),
        valid_until=date.today(), created_by_user_id=user.id,
    ))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_approved_estimate_is_immutable_and_version_conflicts(db_session: Session):
    _org, _user, access, _project, estimate = estimate_fixture(db_session)
    with pytest.raises(AppError) as conflict:
        transition_estimate(db_session, estimate, access, "submit", 99)
    assert conflict.value.code == "VERSION_CONFLICT"
    transition_estimate(db_session, estimate, access, "submit", estimate.version)
    transition_estimate(db_session, estimate, access, "approve", estimate.version)
    with pytest.raises(AppError) as immutable:
        recalculate_estimate(db_session, estimate)
    assert immutable.value.code == "INVALID_ESTIMATE_STATE"
    with pytest.raises(AppError):
        add_estimate_item(db_session, estimate, item_type="option", description="late", quantity=Decimal("1"), unit="lot", unit_price=Decimal("1"))


def test_expired_or_unapproved_estimate_cannot_be_contracted(db_session: Session):
    _org, _user, access, project, estimate = estimate_fixture(db_session)
    with pytest.raises(AppError) as unapproved:
        create_contract(db_session, estimate, project, access, contract_number="C-unapproved", contract_type="development", terms_version="v1")
    assert unapproved.value.code == "INVALID_ESTIMATE_STATE"
    estimate.status = "approved"
    estimate.valid_until = date.today() - timedelta(days=1)
    with pytest.raises(AppError) as expired:
        create_contract(db_session, estimate, project, access, contract_number="C-expired", contract_type="development", terms_version="v1")
    assert expired.value.code == "ESTIMATE_EXPIRED"


def test_contract_requires_scope_and_both_acceptances(db_session: Session):
    _org, _user, access, project, estimate = estimate_fixture(db_session)
    transition_estimate(db_session, estimate, access, "submit", estimate.version)
    transition_estimate(db_session, estimate, access, "approve", estimate.version)
    other_org, _other_user, other_access, other_project = context(db_session, "other-contract")
    with pytest.raises(HTTPException):
        create_contract(db_session, estimate, other_project, other_access, contract_number="C-wrong", contract_type="development", terms_version="v1")
    contract = create_contract(db_session, estimate, project, access, contract_number="C-good", contract_type="development", terms_version="v1")
    accept_contract(db_session, contract, access, party="customer", expected_version=contract.version, request_id=uuid.uuid4())
    assert contract.status == "awaiting_provider"
    accept_contract(db_session, contract, access, party="provider", expected_version=contract.version, request_id=uuid.uuid4())
    assert contract.status == "active"
    assert contract.started_at is not None
    assert other_org.id != contract.organization_id


@pytest.mark.parametrize(("outcome", "expected_status", "project_status"), [("succeeded", "succeeded", "requirements"), ("failed", "failed", "draft"), ("processing", "processing", "draft")])
def test_mock_payment_outcomes(db_session: Session, outcome: str, expected_status: str, project_status: str):
    _org, _user, access, project, estimate, contract = active_contract_fixture(db_session, f"pay-{outcome}")
    provider = MockPaymentProvider([outcome])
    intent = create_contract_payment_intent(db_session, contract, access, provider, idempotency_key=f"idem-{uuid.uuid4()}", expected_amount=estimate.total_amount)
    confirm_contract_payment(db_session, intent, contract, project, access, provider, intent.version)
    assert intent.status == expected_status
    assert project.status == project_status
    if outcome == "failed":
        assert intent.failure_code == "card_declined"
        assert "card" not in (intent.failure_message_sanitized or "").lower()


def test_payment_amount_idempotency_duplicate_and_reconfirm(db_session: Session):
    _org, _user, access, project, estimate, contract = active_contract_fixture(db_session, "payment-guards")
    provider = MockPaymentProvider(["succeeded"])
    key = f"idem-{uuid.uuid4()}"
    with pytest.raises(AppError) as mismatch:
        create_contract_payment_intent(db_session, contract, access, provider, idempotency_key=key, expected_amount=estimate.total_amount + Decimal("1"))
    assert mismatch.value.code == "AMOUNT_MISMATCH"
    intent = create_contract_payment_intent(db_session, contract, access, provider, idempotency_key=key)
    assert create_contract_payment_intent(db_session, contract, access, provider, idempotency_key=key).id == intent.id
    with pytest.raises(AppError) as duplicate:
        create_contract_payment_intent(db_session, contract, access, provider, idempotency_key=f"other-{uuid.uuid4()}")
    assert duplicate.value.code == "DUPLICATE_PAYMENT"
    confirm_contract_payment(db_session, intent, contract, project, access, provider, intent.version)
    with pytest.raises(AppError) as reconfirm:
        confirm_contract_payment(db_session, intent, contract, project, access, provider, intent.version)
    assert reconfirm.value.code == "DUPLICATE_PAYMENT"


def test_provider_unavailable_maps_to_safe_error(db_session: Session):
    _org, _user, access, _project, _estimate, contract = active_contract_fixture(db_session, "provider-down")
    with pytest.raises(AppError) as error:
        create_contract_payment_intent(db_session, contract, access, StripePaymentProviderStub(), idempotency_key=f"idem-{uuid.uuid4()}")
    assert error.value.code == "PAYMENT_PROVIDER_UNAVAILABLE"


def test_payment_method_model_has_no_card_or_cvc_columns():
    columns = set(PaymentMethod.__table__.columns.keys())
    assert "card_number" not in columns
    assert "cvc" not in columns
    assert {"brand", "last4", "expiry_month", "expiry_year"} <= columns


def maintenance_fixture(session: Session):
    organization, user, access, project, _estimate, contract = active_contract_fixture(session, "maintenance", contract_type="maintenance")
    project.status = "production"
    project.current_phase = "production"
    plan = MaintenancePlan(
        name="Standard", code=f"standard-{uuid.uuid4().hex[:8]}", status="active", currency="JPY",
        monthly_price=Decimal("10000"), included_ai_minutes=60, included_human_minutes=30,
        backup_retention_days=30, support_response_hours=8, monitoring_enabled=True, staging_enabled=True,
    )
    session.add(plan)
    session.flush()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    maintenance = create_maintenance_contract(session, project, contract, plan, access, now)
    return organization, user, access, project, contract, maintenance, now


def test_maintenance_delinquency_boundaries_and_no_aws_execution(db_session: Session):
    _org, _user, _access, _project, _contract, maintenance, start = maintenance_fixture(db_session)
    mark_maintenance_payment_failed(db_session, maintenance, start)
    assert maintenance.status == "past_due"
    assert advance_maintenance_delinquency(db_session, maintenance, start + timedelta(days=29, hours=23)) is None
    assert maintenance.status == "past_due"
    assert advance_maintenance_delinquency(db_session, maintenance, start + timedelta(days=30)) is None
    assert maintenance.status == "grace_period"
    assert advance_maintenance_delinquency(db_session, maintenance, start + timedelta(days=60)) is None
    assert maintenance.status == "suspended"
    request = advance_maintenance_delinquency(db_session, maintenance, start + timedelta(days=90))
    assert maintenance.status == "deletion_scheduled"
    assert request is not None and request.status == "pending_first_approval"
    assert request.execution_reference is None


def test_maintenance_recovery_cancels_deletion(db_session: Session):
    _org, _user, _access, _project, _contract, maintenance, start = maintenance_fixture(db_session)
    mark_maintenance_payment_failed(db_session, maintenance, start)
    request = advance_maintenance_delinquency(db_session, maintenance, start + timedelta(days=90))
    recover_maintenance_payment(db_session, maintenance, start + timedelta(days=91))
    assert maintenance.status == "active"
    assert request is not None and request.status == "cancelled"


def test_deletion_requires_two_distinct_approvers(db_session: Session):
    organization, user, access, _project, _contract, maintenance, start = maintenance_fixture(db_session)
    mark_maintenance_payment_failed(db_session, maintenance, start)
    request = advance_maintenance_delinquency(db_session, maintenance, start + timedelta(days=90))
    assert request is not None
    approve_deletion_request(db_session, request, access, start + timedelta(days=90), request.version)
    with pytest.raises(AppError) as same:
        approve_deletion_request(db_session, request, access, start + timedelta(days=90), request.version)
    assert same.value.code == "PAYMENT_ACTION_FORBIDDEN"
    second = User(cognito_sub=f"second-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com", display_name="Second", status="active")
    role = Role(code=f"second-{uuid.uuid4().hex[:20]}", display_name="Second admin", is_system=False)
    membership = OrganizationMembership(organization_id=organization.id, user=second, status="active")
    membership.roles.append(MembershipRole(role=role))
    db_session.add(membership)
    db_session.flush()
    raw = require_organization_access(organization.id, AuthenticatedUser(second), db_session)
    second_access = type(raw)(raw.user, raw.membership, frozenset({"organization_admin"}))
    approve_deletion_request(db_session, request, second_access, start + timedelta(days=90), request.version)
    assert request.status == "approved"
    assert request.execution_reference is None
    assert request.approved_by_first == user.id
    assert request.approved_by_second == second.id


def test_mock_webhook_signature_hash_and_idempotency(db_session: Session):
    organization, _user, _access, _project = context(db_session, "webhook")
    provider = MockPaymentProvider()
    payload = json.dumps({"id": "evt_1", "type": "payment.succeeded", "organization_id": str(organization.id), "card": "must-not-persist"}, separators=(",", ":")).encode()
    with pytest.raises(AppError) as invalid:
        process_mock_webhook(db_session, provider, organization.id, payload, "bad")
    assert invalid.value.code == "AUTHENTICATION_REQUIRED"
    event = process_mock_webhook(db_session, provider, organization.id, payload, provider.sign_webhook(payload))
    assert event.payload_hash
    assert not hasattr(event, "payload")
    with pytest.raises(AppError) as duplicate:
        process_mock_webhook(db_session, provider, organization.id, payload, provider.sign_webhook(payload))
    assert duplicate.value.code == "WEBHOOK_ALREADY_PROCESSED"
    assert db_session.query(PaymentEvent).count() == 1


def test_webhook_out_of_order_does_not_regress_succeeded_payment(db_session: Session):
    organization, _user, access, project, _estimate, contract = active_contract_fixture(db_session, "webhook-order")
    provider = MockPaymentProvider()
    intent = create_contract_payment_intent(db_session, contract, access, provider, idempotency_key=f"idem-{uuid.uuid4()}")
    succeeded = json.dumps({
        "id": "evt_success", "type": "payment_intent.succeeded",
        "organization_id": str(organization.id), "provider_payment_intent_id": intent.provider_payment_intent_id,
    }, separators=(",", ":")).encode()
    failed_late = json.dumps({
        "id": "evt_failed_late", "type": "payment_intent.failed",
        "organization_id": str(organization.id), "provider_payment_intent_id": intent.provider_payment_intent_id,
    }, separators=(",", ":")).encode()
    process_mock_webhook(db_session, provider, organization.id, succeeded, provider.sign_webhook(succeeded))
    process_mock_webhook(db_session, provider, organization.id, failed_late, provider.sign_webhook(failed_late))
    assert intent.status == "succeeded"
    assert project.status == "requirements"


def test_artifact_value_uses_decimal_snapshot_formula():
    value = calculate_artifact_value(
        Decimal("100.00000000"), Decimal("1.20000000"), Decimal("0.90000000"),
        screen_count=10, api_count=5, table_count=2, test_case_count=20,
    )
    assert value == Decimal("135.00000000")
