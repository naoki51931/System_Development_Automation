import json
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.pagination import paginate_query
from app.api.schemas import EstimateCursorPage
from app.auth.dependencies import (
    AuthenticatedUser,
    get_current_user,
    get_session,
    require_organization_access,
)
from app.auth.permissions import Permission, require_permission
from app.errors import AppError
from app.models.billing import (
    Contract,
    Estimate,
    EstimateItem,
    MaintenanceContract,
    MaintenancePlan,
    PaymentIntent,
)
from app.models.project import Project
from app.services.billing import (
    CUSTOMER_ROLES,
    PAYMENT_ROLES,
    WRITE_ROLES,
    accept_contract,
    create_contract,
    create_contract_payment_intent,
    create_estimate,
    create_maintenance_contract,
    confirm_contract_payment,
    process_mock_webhook,
    transition_estimate,
)
from app.services.payment_providers import MockPaymentProvider, PaymentProvider

router = APIRouter(prefix="/api/v1", tags=["estimate-contract-payment"])


class EstimateItemInput(BaseModel):
    item_type: str
    phase: str | None = None
    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=8)
    unit: str = Field(min_length=1, max_length=30)
    unit_price: Decimal = Field(max_digits=18, decimal_places=8)
    source_type: str = "manual"
    source_reference_id: uuid.UUID | None = None


class EstimateCreateInput(BaseModel):
    estimate_number: str = Field(min_length=1, max_length=50)
    currency: str = Field(default="JPY", pattern=r"^[A-Z]{3}$")
    valid_until: date
    items: list[EstimateItemInput] = Field(default_factory=list)
    include_ai_runs: bool = True
    include_artifacts: bool = True


class VersionInput(BaseModel):
    version: int = Field(ge=1)


class ContractCreateInput(BaseModel):
    contract_number: str = Field(min_length=1, max_length=50)
    contract_type: str = "development"
    terms_version: str = Field(min_length=1, max_length=50)
    document_artifact_version_id: uuid.UUID | None = None


class PaymentIntentCreateInput(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=255)
    expected_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=8
    )


class MaintenanceContractCreateInput(BaseModel):
    contract_id: uuid.UUID
    maintenance_plan_id: uuid.UUID


def get_payment_provider(request: Request) -> PaymentProvider:
    provider = getattr(request.app.state, "payment_provider", None)
    if provider is None:
        provider = MockPaymentProvider(
            outcomes=[
                item
                for item in os.getenv("MOCK_PAYMENT_OUTCOMES", "succeeded").split(",")
                if item
            ],
            webhook_secret=os.getenv("MOCK_WEBHOOK_SECRET"),
        )
        request.app.state.payment_provider = provider
    return provider


def estimate_json(
    estimate: Estimate, session: Session, include_items: bool = False
) -> dict[str, object]:
    result: dict[str, object] = {
        "id": str(estimate.id),
        "organization_id": str(estimate.organization_id),
        "project_id": str(estimate.project_id),
        "estimate_number": estimate.estimate_number,
        "status": estimate.status,
        "currency": estimate.currency,
        "subtotal": str(estimate.subtotal),
        "tax_amount": str(estimate.tax_amount),
        "total_amount": str(estimate.total_amount),
        "valid_until": estimate.valid_until.isoformat(),
        "version": estimate.version,
    }
    if include_items:
        items = session.scalars(
            select(EstimateItem)
            .where(EstimateItem.estimate_id == estimate.id)
            .order_by(EstimateItem.display_order)
        ).all()
        result["items"] = [
            {
                "id": str(item.id),
                "item_type": item.item_type,
                "description": item.description,
                "quantity": str(item.quantity),
                "unit": item.unit,
                "unit_price": str(item.unit_price),
                "amount": str(item.amount),
                "source_type": item.source_type,
            }
            for item in items
        ]
    return result


def contract_json(contract: Contract) -> dict[str, object]:
    return {
        "id": str(contract.id),
        "organization_id": str(contract.organization_id),
        "project_id": str(contract.project_id),
        "estimate_id": str(contract.estimate_id),
        "contract_number": contract.contract_number,
        "status": contract.status,
        "contract_type": contract.contract_type,
        "terms_version": contract.terms_version,
        "version": contract.version,
    }


def payment_json(intent: PaymentIntent) -> dict[str, object]:
    return {
        "id": str(intent.id),
        "organization_id": str(intent.organization_id),
        "project_id": str(intent.project_id),
        "contract_id": str(intent.contract_id),
        "provider": intent.provider,
        "status": intent.status,
        "currency": intent.currency,
        "amount": str(intent.amount),
        "version": intent.version,
        "failure_code": intent.failure_code,
        "confirmed_at": intent.confirmed_at.isoformat()
        if intent.confirmed_at
        else None,
    }


def maintenance_json(contract: MaintenanceContract) -> dict[str, object]:
    return {
        "id": str(contract.id),
        "organization_id": str(contract.organization_id),
        "project_id": str(contract.project_id),
        "contract_id": str(contract.contract_id),
        "maintenance_plan_id": str(contract.maintenance_plan_id),
        "status": contract.status,
        "current_period_start": contract.current_period_start.isoformat()
        if contract.current_period_start
        else None,
        "current_period_end": contract.current_period_end.isoformat()
        if contract.current_period_end
        else None,
        "version": contract.version,
    }


def get_project_context(
    session: Session, project_id: uuid.UUID, authenticated: AuthenticatedUser
):
    project = session.get(Project, project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", "Project not found")
    access = require_organization_access(
        project.organization_id, authenticated, session
    )
    return project, access


@router.post("/projects/{project_id}/estimates", status_code=status.HTTP_201_CREATED)
def post_estimate(
    project_id: uuid.UUID,
    payload: EstimateCreateInput,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    project, access = get_project_context(session, project_id, authenticated)
    require_permission(session, access, Permission.CONTRACT_CREATE, project.id)
    values = payload.model_dump()
    values["items"] = [item.model_dump() for item in payload.items]
    estimate = create_estimate(session, project, access, **values)
    session.commit()
    return estimate_json(estimate, session, True)


@router.get("/projects/{project_id}/estimates", response_model=EstimateCursorPage)
def list_estimates(
    project_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    cursor: str | None = None,
    page_size: int = Query(50, ge=1, le=100),
):
    project, _access = get_project_context(session, project_id, authenticated)
    statement = select(Estimate).where(
        Estimate.organization_id == project.organization_id,
        Estimate.project_id == project.id,
    )
    return paginate_query(
        session,
        statement,
        Estimate,
        cursor,
        page_size,
        lambda item: estimate_json(item, session),
        scope=f"estimates:{project.organization_id}:{project.id}",
    )


@router.get("/estimates/{estimate_id}")
def get_estimate(
    estimate_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    estimate = session.get(Estimate, estimate_id)
    if estimate is None:
        raise AppError("RESOURCE_NOT_FOUND", "Estimate not found")
    require_organization_access(estimate.organization_id, authenticated, session)
    return estimate_json(estimate, session, True)


def estimate_action(
    estimate_id: uuid.UUID,
    action: str,
    payload: VersionInput,
    authenticated: AuthenticatedUser,
    session: Session,
):
    estimate = session.get(Estimate, estimate_id)
    if estimate is None:
        raise AppError("RESOURCE_NOT_FOUND", "Estimate not found")
    access = require_organization_access(
        estimate.organization_id, authenticated, session
    )
    required = (
        Permission.CONTRACT_UPDATE
        if action in {"approve", "reject"}
        else Permission.CONTRACT_CREATE
    )
    require_permission(session, access, required, estimate.project_id)
    transition_estimate(session, estimate, access, action, payload.version)
    session.commit()
    return estimate_json(estimate, session)


@router.post("/estimates/{estimate_id}/submit")
def submit_estimate(
    estimate_id: uuid.UUID,
    payload: VersionInput,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return estimate_action(estimate_id, "submit", payload, authenticated, session)


@router.post("/estimates/{estimate_id}/approve")
def approve_estimate(
    estimate_id: uuid.UUID,
    payload: VersionInput,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return estimate_action(estimate_id, "approve", payload, authenticated, session)


@router.post("/estimates/{estimate_id}/reject")
def reject_estimate(
    estimate_id: uuid.UUID,
    payload: VersionInput,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return estimate_action(estimate_id, "reject", payload, authenticated, session)


@router.post("/estimates/{estimate_id}/contracts", status_code=status.HTTP_201_CREATED)
def post_contract(
    estimate_id: uuid.UUID,
    payload: ContractCreateInput,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    estimate = session.get(Estimate, estimate_id)
    if estimate is None:
        raise AppError("RESOURCE_NOT_FOUND", "Estimate not found")
    access = require_organization_access(
        estimate.organization_id, authenticated, session, WRITE_ROLES
    )
    require_permission(session, access, Permission.CONTRACT_CREATE, estimate.project_id)
    project = session.get(Project, estimate.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", "Project not found")
    contract = create_contract(
        session, estimate, project, access, **payload.model_dump()
    )
    session.commit()
    return contract_json(contract)


@router.get("/contracts/{contract_id}")
def get_contract(
    contract_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    contract = session.get(Contract, contract_id)
    if contract is None:
        raise AppError("PAYMENT_RESOURCE_NOT_FOUND", "Contract not found")
    require_organization_access(contract.organization_id, authenticated, session)
    return contract_json(contract)


def contract_accept(
    contract_id: uuid.UUID,
    party: str,
    payload: VersionInput,
    authenticated: AuthenticatedUser,
    session: Session,
):
    contract = session.get(Contract, contract_id)
    if contract is None:
        raise AppError("PAYMENT_RESOURCE_NOT_FOUND", "Contract not found")
    roles = CUSTOMER_ROLES if party == "customer" else WRITE_ROLES
    access = require_organization_access(
        contract.organization_id, authenticated, session, roles
    )
    require_permission(session, access, Permission.CONTRACT_UPDATE, contract.project_id)
    accept_contract(
        session,
        contract,
        access,
        party=party,
        expected_version=payload.version,
        request_id=uuid.uuid4(),
    )
    session.commit()
    return contract_json(contract)


@router.post("/contracts/{contract_id}/customer-accept")
def customer_accept(
    contract_id: uuid.UUID,
    payload: VersionInput,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return contract_accept(contract_id, "customer", payload, authenticated, session)


@router.post("/contracts/{contract_id}/provider-accept")
def provider_accept(
    contract_id: uuid.UUID,
    payload: VersionInput,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return contract_accept(contract_id, "provider", payload, authenticated, session)


@router.post(
    "/contracts/{contract_id}/payment-intents", status_code=status.HTTP_201_CREATED
)
def post_payment_intent(
    contract_id: uuid.UUID,
    payload: PaymentIntentCreateInput,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    provider: Annotated[PaymentProvider, Depends(get_payment_provider)],
):
    contract = session.get(Contract, contract_id)
    if contract is None:
        raise AppError("PAYMENT_RESOURCE_NOT_FOUND", "Contract not found")
    access = require_organization_access(
        contract.organization_id, authenticated, session, PAYMENT_ROLES
    )
    require_permission(session, access, Permission.PAYMENT_UPDATE, contract.project_id)
    intent = create_contract_payment_intent(
        session, contract, access, provider, **payload.model_dump()
    )
    session.commit()
    return payment_json(intent)


@router.post("/payment-intents/{payment_intent_id}/confirm")
def confirm_payment_intent(
    payment_intent_id: uuid.UUID,
    payload: VersionInput,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    provider: Annotated[PaymentProvider, Depends(get_payment_provider)],
):
    intent = session.get(PaymentIntent, payment_intent_id)
    if intent is None:
        raise AppError("PAYMENT_RESOURCE_NOT_FOUND", "Payment intent not found")
    access = require_organization_access(
        intent.organization_id, authenticated, session, PAYMENT_ROLES
    )
    require_permission(session, access, Permission.PAYMENT_UPDATE, intent.project_id)
    contract = session.get(Contract, intent.contract_id)
    project = session.get(Project, intent.project_id)
    if contract is None or project is None:
        raise AppError("PAYMENT_RESOURCE_NOT_FOUND", "Payment scope not found")
    confirm_contract_payment(
        session, intent, contract, project, access, provider, payload.version
    )
    session.commit()
    return payment_json(intent)


@router.get("/payment-intents/{payment_intent_id}")
def get_payment_intent(
    payment_intent_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    intent = session.get(PaymentIntent, payment_intent_id)
    if intent is None:
        raise AppError("PAYMENT_RESOURCE_NOT_FOUND", "Payment intent not found")
    require_organization_access(intent.organization_id, authenticated, session)
    return payment_json(intent)


@router.get("/maintenance-plans")
def list_maintenance_plans(
    organization_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    require_organization_access(organization_id, authenticated, session)
    plans = session.scalars(
        select(MaintenancePlan)
        .where(
            MaintenancePlan.status == "active",
            (MaintenancePlan.organization_id == organization_id)
            | MaintenancePlan.organization_id.is_(None),
        )
        .order_by(MaintenancePlan.code)
    ).all()
    return [
        {
            "id": str(plan.id),
            "name": plan.name,
            "code": plan.code,
            "currency": plan.currency,
            "monthly_price": str(plan.monthly_price),
            "version": plan.version,
        }
        for plan in plans
    ]


@router.post(
    "/projects/{project_id}/maintenance-contracts", status_code=status.HTTP_201_CREATED
)
def post_maintenance_contract(
    project_id: uuid.UUID,
    payload: MaintenanceContractCreateInput,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    project, access = get_project_context(session, project_id, authenticated)
    require_permission(session, access, Permission.CONTRACT_CREATE, project.id)
    contract = session.get(Contract, payload.contract_id)
    plan = session.get(MaintenancePlan, payload.maintenance_plan_id)
    if contract is None or plan is None:
        raise AppError(
            "PAYMENT_RESOURCE_NOT_FOUND", "Maintenance contract input not found"
        )
    maintenance = create_maintenance_contract(
        session, project, contract, plan, access, datetime.now(timezone.utc)
    )
    session.commit()
    return maintenance_json(maintenance)


@router.get("/maintenance-contracts/{maintenance_contract_id}")
def get_maintenance_contract(
    maintenance_contract_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    contract = session.get(MaintenanceContract, maintenance_contract_id)
    if contract is None:
        raise AppError("PAYMENT_RESOURCE_NOT_FOUND", "Maintenance contract not found")
    require_organization_access(contract.organization_id, authenticated, session)
    return maintenance_json(contract)


@router.post("/maintenance-contracts/{maintenance_contract_id}/cancel")
def cancel_maintenance_contract(
    maintenance_contract_id: uuid.UUID,
    payload: VersionInput,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    contract = session.get(MaintenanceContract, maintenance_contract_id)
    if contract is None:
        raise AppError("PAYMENT_RESOURCE_NOT_FOUND", "Maintenance contract not found")
    access = require_organization_access(
        contract.organization_id, authenticated, session, WRITE_ROLES
    )
    require_permission(session, access, Permission.CONTRACT_UPDATE, contract.project_id)
    if contract.version != payload.version:
        raise AppError("VERSION_CONFLICT", "Resource was updated by another request")
    if contract.status == "terminated":
        raise AppError(
            "INVALID_STATE_TRANSITION", "Maintenance contract is already terminated"
        )
    contract.status = "terminated"
    contract.terminated_at = datetime.now(timezone.utc)
    session.commit()
    return maintenance_json(contract)


@router.post("/payment-webhooks/mock")
async def mock_webhook(
    request: Request,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    provider: Annotated[PaymentProvider, Depends(get_payment_provider)],
):
    payload = await request.body()
    try:
        organization_id = uuid.UUID(str(json.loads(payload)["organization_id"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise AppError("INVALID_REQUEST", "Webhook organization is invalid") from exc
    require_organization_access(organization_id, authenticated, session)
    signature = request.headers.get("X-Mock-Signature", "")
    event = process_mock_webhook(session, provider, organization_id, payload, signature)
    session.commit()
    return {
        "id": str(event.id),
        "provider_event_id": event.provider_event_id,
        "status": event.status,
        "payload_hash": event.payload_hash,
    }
