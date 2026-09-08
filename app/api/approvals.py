import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import ApprovalRequest, DecisionRequest
from app.auth.dependencies import (
    AuthenticatedUser,
    get_current_user,
    get_session,
    require_organization_access,
)
from app.auth.permissions import Permission, ProtectedAction, require_permission
from app.models import ProtectedApproval
from app.services.approvals import decide_approval, request_approval

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


def approval_json(item: ProtectedApproval) -> dict[str, object]:
    return {
        "id": str(item.id),
        "organization_id": str(item.organization_id),
        "project_id": str(item.project_id) if item.project_id else None,
        "requested_by": str(item.requested_by_user_id),
        "decided_by": str(item.decided_by_user_id) if item.decided_by_user_id else None,
        "action": item.action,
        "resource_type": item.resource_type,
        "resource_id": str(item.resource_id) if item.resource_id else None,
        "target_version": item.target_version,
        "plan_checksum": item.plan_checksum,
        "artifact_digest": item.artifact_digest,
        "status": item.status,
        "requires_distinct_approver": item.requires_distinct_approver,
        "requested_at": item.requested_at.isoformat() if item.requested_at else None,
        "decided_at": item.decided_at.isoformat() if item.decided_at else None,
        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
    }


@router.get("")
def list_approvals(
    organization_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    access = require_organization_access(organization_id, authenticated, session)
    require_permission(session, access, Permission.APPROVAL_READ)
    return [
        approval_json(x)
        for x in session.scalars(
            select(ProtectedApproval)
            .where(ProtectedApproval.organization_id == organization_id)
            .order_by(ProtectedApproval.requested_at.desc())
        ).all()
    ]


@router.post("", status_code=201)
def create_approval(
    payload: ApprovalRequest,
    request: Request,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    access = require_organization_access(
        payload.organization_id, authenticated, session
    )
    try:
        action = ProtectedAction(payload.action)
    except ValueError as exc:
        raise HTTPException(422, "Unknown protected action") from exc
    item = request_approval(
        session,
        access,
        organization_id=payload.organization_id,
        project_id=payload.project_id,
        action=action,
        request_id=uuid.uuid4(),
        ip_address=request.client.host if request.client else None,
        **payload.model_dump(exclude={"action", "organization_id", "project_id"}),
    )
    session.commit()
    return approval_json(item)


def decide(
    approval_id: uuid.UUID,
    approve: bool,
    request: Request,
    payload: DecisionRequest,
    authenticated: AuthenticatedUser,
    session: Session,
):
    item = session.get(ProtectedApproval, approval_id)
    if item is None:
        raise HTTPException(404, "Approval not found")
    access = require_organization_access(item.organization_id, authenticated, session)
    decide_approval(
        session,
        access,
        item,
        approve=approve,
        reason=payload.comment,
        request_id=uuid.uuid4(),
        ip_address=request.client.host if request.client else None,
    )
    session.commit()
    return approval_json(item)


@router.post("/{approval_id}/approve")
def approve(
    approval_id: uuid.UUID,
    payload: DecisionRequest,
    request: Request,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return decide(approval_id, True, request, payload, authenticated, session)


@router.post("/{approval_id}/reject")
def reject(
    approval_id: uuid.UUID,
    payload: DecisionRequest,
    request: Request,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return decide(approval_id, False, request, payload, authenticated, session)
