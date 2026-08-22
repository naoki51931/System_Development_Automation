import secrets
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth.dependencies import (
    AuthenticatedUser,
    get_current_user,
    get_session,
    require_organization_access,
)
from app.auth.verifier import LocalAuthProvider
from app.core.config import get_settings
from app.models import Organization, OrganizationMembership, User

router = APIRouter(prefix="/api/v1/auth", tags=["local-auth"])


class LoginInput(BaseModel):
    user_id: uuid.UUID


class SwitchInput(BaseModel):
    organization_id: uuid.UUID


def enabled():
    settings = get_settings()
    if (
        settings.environment.lower() in {"staging", "production", "prod"}
        or not settings.local_auth_enabled
    ):
        raise HTTPException(404, "Local authentication is disabled")
    return settings


def csrf_check(request: Request):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        cookie = request.cookies.get("sn_csrf")
        header = request.headers.get("X-CSRF-Token")
        if request.cookies.get("sn_session") and (
            not cookie or not secrets.compare_digest(cookie, header or "")
        ):
            raise HTTPException(403, "CSRF validation failed")


@router.get("/local/users")
def local_users(session: Annotated[Session, Depends(get_session)]):
    enabled()
    users = session.scalars(
        select(User).where(User.status == "active").order_by(User.email)
    ).all()
    return [
        {"id": str(x.id), "email": x.email, "display_name": x.display_name}
        for x in users
    ]


@router.post("/local/login")
def login(
    payload: LoginInput,
    response: Response,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
):
    settings = enabled()
    user = session.get(User, payload.user_id)
    if not user or user.status != "active":
        raise HTTPException(401, "User unavailable")
    provider = LocalAuthProvider(settings.local_auth_secret)
    request.app.state.token_verifier = provider
    csrf = secrets.token_urlsafe(32)
    secure = settings.environment.lower() not in {"development", "test"}
    response.set_cookie(
        "sn_session",
        provider.issue(user.cognito_sub),
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=3600,
        path="/",
    )
    response.set_cookie(
        "sn_csrf",
        csrf,
        httponly=False,
        secure=secure,
        samesite="lax",
        max_age=3600,
        path="/",
    )
    return {
        "user": {"id": str(user.id), "display_name": user.display_name},
        "csrf_token": csrf,
    }


@router.post("/logout", dependencies=[Depends(csrf_check)])
def logout(response: Response):
    response.delete_cookie("sn_session", path="/")
    response.delete_cookie("sn_csrf", path="/")
    return {"status": "logged_out"}


@router.get("/me")
def me(
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rows = session.execute(
        select(OrganizationMembership, Organization)
        .join(Organization)
        .where(
            OrganizationMembership.user_id == authenticated.user.id,
            OrganizationMembership.status == "active",
        )
    ).all()
    return {
        "id": str(authenticated.user.id),
        "display_name": authenticated.user.display_name,
        "organizations": [
            {
                "id": str(o.id),
                "name": o.name,
                "roles": sorted(item.role.code for item in membership.roles),
            }
            for membership, o in rows
        ],
    }


@router.post("/switch-organization", dependencies=[Depends(csrf_check)])
def switch(
    payload: SwitchInput,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    access = require_organization_access(
        payload.organization_id, authenticated, session
    )
    return {
        "organization_id": str(payload.organization_id),
        "roles": sorted(access.role_codes),
    }
