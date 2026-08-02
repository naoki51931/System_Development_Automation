import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.auth.dependencies import (
    AuthenticatedUser,
    ensure_resource_organization,
    get_current_user,
    get_session,
    require_organization_access,
)
from app.auth.verifier import (
    CognitoAccessTokenVerifier,
    StaticAccessTokenVerifier,
    TokenVerificationError,
    VerifiedAccessToken,
)
from app.models import MembershipRole, Organization, OrganizationMembership, Role, User


def verified(subject: str) -> VerifiedAccessToken:
    return VerifiedAccessToken(
        subject=subject,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        claims={"sub": subject, "token_use": "access"},
    )


def auth_client(db_session: Session, tokens: dict[str, VerifiedAccessToken]) -> TestClient:
    app = FastAPI()
    app.state.session_factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    app.state.token_verifier = StaticAccessTokenVerifier(tokens)

    @app.get("/me")
    def me(authenticated: AuthenticatedUser = Depends(get_current_user)):
        return {"id": str(authenticated.user.id)}

    @app.get("/organizations/{organization_id}/protected")
    def protected(
        organization_id: uuid.UUID,
        resource_organization_id: uuid.UUID,
        authenticated: AuthenticatedUser = Depends(get_current_user),
        session: Session = Depends(get_session),
    ):
        access = require_organization_access(
            organization_id, authenticated, session, frozenset({"viewer"})
        )
        ensure_resource_organization(access, resource_organization_id)
        return {"ok": True}

    return TestClient(app)


def test_invalid_jwt_returns_401(db_session: Session):
    response = auth_client(db_session, {}).get("/me", headers={"Authorization": "Bearer bad"})
    assert response.status_code == 401


def test_inactive_user_returns_401(db_session: Session):
    account = User(
        cognito_sub="inactive-sub",
        email="inactive@example.com",
        display_name="Inactive",
        status="inactive",
    )
    db_session.add(account)
    db_session.commit()
    response = auth_client(db_session, {"valid": verified("inactive-sub")}).get(
        "/me", headers={"Authorization": "Bearer valid"}
    )
    assert response.status_code == 401


def test_membership_role_and_resource_tenant_boundaries(db_session: Session):
    account = User(
        cognito_sub="active-sub", email="active@example.com", display_name="Active", status="active"
    )
    organization = Organization(name="Allowed", status="active")
    other = Organization(name="Other", status="active")
    viewer = Role(code="viewer", display_name="Viewer", is_system=True)
    membership = OrganizationMembership(organization=organization, user=account, status="active")
    membership.roles.append(MembershipRole(role=viewer))
    db_session.add_all([membership, other])
    db_session.commit()
    client = auth_client(db_session, {"valid": verified("active-sub")})
    headers = {"Authorization": "Bearer valid"}

    assert client.get(
        f"/organizations/{organization.id}/protected",
        params={"resource_organization_id": organization.id},
        headers=headers,
    ).status_code == 200
    assert client.get(
        f"/organizations/{other.id}/protected",
        params={"resource_organization_id": other.id},
        headers=headers,
    ).status_code == 403
    assert client.get(
        f"/organizations/{organization.id}/protected",
        params={"resource_organization_id": other.id},
        headers=headers,
    ).status_code == 403


def test_role_shortage_returns_403(db_session: Session):
    account = User(cognito_sub="no-role", email="norole@example.com", display_name="No Role", status="active")
    organization = Organization(name="No Role Org", status="active")
    db_session.add(OrganizationMembership(organization=organization, user=account, status="active"))
    db_session.commit()
    client = auth_client(db_session, {"valid": verified("no-role")})
    response = client.get(
        f"/organizations/{organization.id}/protected",
        params={"resource_organization_id": organization.id},
        headers={"Authorization": "Bearer valid"},
    )
    assert response.status_code == 403


def test_cognito_access_token_validates_signature_issuer_client_and_token_use():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = "https://cognito-idp.eu-west-2.amazonaws.com/pool"
    client_id = "client-id"
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "cognito-sub",
        "iss": issuer,
        "client_id": client_id,
        "token_use": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "key-1"})
    verifier = CognitoAccessTokenVerifier(
        issuer=issuer, client_id=client_id, key_provider=lambda _kid: private_key.public_key()
    )
    assert verifier.verify(token).subject == "cognito-sub"

    invalid = jwt.encode(
        {**claims, "token_use": "id"}, private_key, algorithm="RS256", headers={"kid": "key-1"}
    )
    with pytest.raises(TokenVerificationError):
        verifier.verify(invalid)
