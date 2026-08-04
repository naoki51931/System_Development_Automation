from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.auth.verifier import StaticAccessTokenVerifier, VerifiedAccessToken
from app.main import create_app
from app.models import MembershipRole, Organization, OrganizationMembership, Role, User


def client_for(session: Session, user: User, token: str = "valid") -> TestClient:
    app = create_app()
    app.state.session_factory = sessionmaker(
        bind=session.get_bind(), expire_on_commit=False
    )
    app.state.token_verifier = StaticAccessTokenVerifier(
        {
            token: VerifiedAccessToken(
                subject=user.cognito_sub,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                claims={"sub": user.cognito_sub},
            )
        }
    )
    return TestClient(app)


def test_project_api_rejects_unrelated_tenant_and_unaffiliated_creator(
    db_session: Session,
):
    allowed = Organization(name="Allowed API", status="active")
    denied = Organization(name="Denied API", status="active")
    member = User(
        cognito_sub="api-member",
        email="api-member@example.com",
        display_name="Member",
        status="active",
    )
    outsider = User(
        cognito_sub="api-outsider",
        email="api-outsider@example.com",
        display_name="Outsider",
        status="active",
    )
    role = Role(code="organization_admin", display_name="Admin", is_system=True)
    membership = OrganizationMembership(
        organization=allowed, user=member, status="active"
    )
    membership.roles.append(MembershipRole(role=role))
    db_session.add_all([membership, denied, outsider])
    db_session.commit()

    member_client = client_for(db_session, member)
    created = member_client.post(
        "/api/v1/projects",
        headers={"Authorization": "Bearer valid"},
        json={
            "organization_id": str(allowed.id),
            "project_code": "API-1",
            "name": "API Project",
        },
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    outsider_client = client_for(db_session, outsider)
    assert (
        outsider_client.get(
            f"/api/v1/projects/{project_id}", headers={"Authorization": "Bearer valid"}
        ).status_code
        == 403
    )
    assert (
        outsider_client.post(
            "/api/v1/projects",
            headers={"Authorization": "Bearer valid"},
            json={
                "organization_id": str(denied.id),
                "project_code": "NO",
                "name": "Denied",
            },
        ).status_code
        == 403
    )
