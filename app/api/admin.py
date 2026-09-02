import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from app.auth.dependencies import (
    AuthenticatedUser,
    get_current_user,
    get_session,
    require_organization_access,
)
from app.models import (
    AuditLog,
    MembershipRole,
    OrganizationMembership,
    OutboxEvent,
    Role,
)
from app.workers.outbox import retry_dead_letter
from app.audit import record_audit_log
from app.auth.permissions import Permission, require_permission

router = APIRouter(prefix="/api/v1/admin", tags=["administration"])
ADMIN = frozenset({"organization_owner", "organization_admin"})


class RoleUpdate(BaseModel):
    role_codes: list[str]


def ensure_last_owner(
    session: Session,
    membership: OrganizationMembership,
    actor_user_id: uuid.UUID,
    new_roles: set[str],
) -> None:
    current = {x.role.code for x in membership.roles}
    if (
        membership.user_id == actor_user_id
        and "organization_owner" in current
        and "organization_owner" not in new_roles
    ):
        owner_count = session.scalar(
            select(func.count())
            .select_from(MembershipRole)
            .join(Role)
            .join(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == membership.organization_id,
                OrganizationMembership.status == "active",
                Role.code == "organization_owner",
            )
        )
        if owner_count <= 1:
            raise HTTPException(
                409,
                detail={
                    "code": "LAST_ORGANIZATION_OWNER",
                    "message": "最後のorganization_owner権限は外せません",
                },
            )


def access(org_id, auth, session):
    return require_organization_access(org_id, auth, session, ADMIN)


@router.get("/users")
def users(
    organization_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    access(organization_id, authenticated, session)
    rows = session.scalars(
        select(OrganizationMembership)
        .options(
            selectinload(OrganizationMembership.user),
            selectinload(OrganizationMembership.roles).selectinload(
                MembershipRole.role
            ),
        )
        .where(OrganizationMembership.organization_id == organization_id)
        .order_by(OrganizationMembership.created_at)
    ).all()
    return [
        {
            "membership_id": str(x.id),
            "user_id": str(x.user_id),
            "display_name": x.user.display_name,
            "email": x.user.email,
            "status": x.status,
            "roles": sorted(r.role.code for r in x.roles),
        }
        for x in rows
    ]


@router.put("/memberships/{membership_id}/roles")
def roles(
    membership_id: uuid.UUID,
    payload: RoleUpdate,
    request: Request,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    membership = session.scalar(
        select(OrganizationMembership)
        .options(
            selectinload(OrganizationMembership.roles).selectinload(MembershipRole.role)
        )
        .where(OrganizationMembership.id == membership_id)
    )
    if not membership:
        raise HTTPException(404, "Membership not found")
    membership_access = access(membership.organization_id, authenticated, session)
    require_permission(session, membership_access, Permission.PERMISSION_CHANGE)
    ensure_last_owner(
        session, membership, authenticated.user.id, set(payload.role_codes)
    )
    role_rows = session.scalars(
        select(Role).where(
            Role.code.in_(payload.role_codes), Role.code != "system_admin"
        )
    ).all()
    if len(role_rows) != len(set(payload.role_codes)):
        raise HTTPException(422, "Unknown or system role")
    before = sorted(r.role.code for r in membership.roles)
    membership.roles.clear()
    membership.roles.extend(MembershipRole(role=x) for x in role_rows)
    record_audit_log(
        session,
        organization_id=membership.organization_id,
        actor_user_id=authenticated.user.id,
        action="permission.change",
        resource_type="organization_membership",
        resource_id=membership.id,
        request_id=uuid.uuid4(),
        before={"roles": before},
        after={"roles": sorted(payload.role_codes)},
        ip_address=request.client.host if request.client else None,
        result="success",
    )
    session.commit()
    return {"roles": sorted(payload.role_codes)}


@router.get("/audit-logs")
def audits(
    organization_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(50, ge=1, le=100),
):
    access(organization_id, authenticated, session)
    rows = session.scalars(
        select(AuditLog)
        .where(AuditLog.organization_id == organization_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": str(x.id),
            "action": x.action,
            "resource_type": x.resource_type,
            "created_at": x.created_at.isoformat(),
        }
        for x in rows
    ]


@router.get("/dead-letters")
def dead_letters(
    organization_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    access(organization_id, authenticated, session)
    rows = session.scalars(
        select(OutboxEvent)
        .where(
            OutboxEvent.organization_id == organization_id,
            OutboxEvent.status == "dead_letter",
        )
        .order_by(OutboxEvent.dead_lettered_at.desc())
    ).all()
    return [
        {
            "id": str(x.id),
            "event_type": x.event_type,
            "attempt_count": x.attempt_count,
            "last_error_code": x.last_error_code,
            "dead_lettered_at": x.dead_lettered_at.isoformat()
            if x.dead_lettered_at
            else None,
        }
        for x in rows
    ]


@router.post("/dead-letters/{job_id}/retry")
def retry(
    job_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    job = session.get(OutboxEvent, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    access(job.organization_id, authenticated, session)
    retry_dead_letter(session, job)
    session.commit()
    return {"status": job.status}
