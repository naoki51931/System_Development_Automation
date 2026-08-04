import uuid
from dataclasses import dataclass
from time import perf_counter
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.auth.verifier import AccessTokenVerifier, TokenVerificationError
from app.models import MembershipRole, OrganizationMembership, User
from app.performance_timing import add_duration

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    user: User


@dataclass(frozen=True)
class OrganizationAccess:
    user: User
    membership: OrganizationMembership
    role_codes: frozenset[str]


def get_session(request: Request):  # type: ignore[no-untyped-def]
    started_at = perf_counter()
    factory: sessionmaker[Session] | None = getattr(
        request.app.state, "session_factory", None
    )
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )
    session = factory()
    add_duration("db_session", started_at)
    try:
        yield session
    finally:
        session.close()


def get_token_verifier(request: Request) -> AccessTokenVerifier:
    verifier: AccessTokenVerifier | None = getattr(
        request.app.state, "token_verifier", None
    )
    if verifier is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth unavailable"
        )
    return verifier


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    verifier: Annotated[AccessTokenVerifier, Depends(get_token_verifier)],
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> AuthenticatedUser:
    started_at = perf_counter()
    raw_token = (
        credentials.credentials
        if credentials and credentials.scheme.lower() == "bearer"
        else request.cookies.get("sn_session")
    )
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    try:
        token = verifier.verify(raw_token)
    except TokenVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token"
        ) from exc

    user = session.scalar(select(User).where(User.cognito_sub == token.subject))
    if user is None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User unavailable"
        )
    result = AuthenticatedUser(user=user)
    add_duration("auth", started_at)
    return result


def require_organization_access(
    organization_id: uuid.UUID,
    authenticated: AuthenticatedUser,
    session: Session,
    required_roles: frozenset[str] = frozenset(),
) -> OrganizationAccess:
    started_at = perf_counter()
    membership = session.scalar(
        select(OrganizationMembership)
        .options(
            selectinload(OrganizationMembership.roles).selectinload(MembershipRole.role)
        )
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == authenticated.user.id,
            OrganizationMembership.status == "active",
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Organization access denied"
        )
    role_codes = frozenset(item.role.code for item in membership.roles)
    if required_roles and role_codes.isdisjoint(required_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied"
        )
    result = OrganizationAccess(authenticated.user, membership, role_codes)
    add_duration("authorization", started_at)
    return result


def ensure_resource_organization(
    access: OrganizationAccess, resource_organization_id: uuid.UUID
) -> None:
    if access.membership.organization_id != resource_organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Resource access denied"
        )
