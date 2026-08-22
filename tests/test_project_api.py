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


def test_pm_can_start_estimate_with_version_and_customer_cannot(db_session: Session):
    organization = Organization(name="Estimate transition", status="active")
    pm = User(
        cognito_sub="estimate-pm",
        email="estimate-pm@example.com",
        display_name="PM",
        status="active",
    )
    customer = User(
        cognito_sub="estimate-customer",
        email="estimate-customer@example.com",
        display_name="Customer",
        status="active",
    )
    pm_role = Role(code="project_manager", display_name="PM", is_system=True)
    customer_role = Role(code="customer", display_name="Customer", is_system=True)
    pm_membership = OrganizationMembership(
        organization=organization, user=pm, status="active"
    )
    pm_membership.roles.append(MembershipRole(role=pm_role))
    customer_membership = OrganizationMembership(
        organization=organization, user=customer, status="active"
    )
    customer_membership.roles.append(MembershipRole(role=customer_role))
    db_session.add_all([pm_membership, customer_membership])
    db_session.commit()

    pm_client = client_for(db_session, pm, "pm-token")
    created = pm_client.post(
        "/api/v1/projects",
        headers={"Authorization": "Bearer pm-token"},
        json={
            "organization_id": str(organization.id),
            "project_code": "ESTIMATE-1",
            "name": "Estimate transition",
        },
    )
    assert created.status_code == 201
    project = created.json()
    assert project["version"] == 1

    customer_client = client_for(db_session, customer, "customer-token")
    forbidden = customer_client.post(
        f"/api/v1/projects/{project['id']}/start-estimate",
        headers={"Authorization": "Bearer customer-token"},
        json={"version": project["version"]},
    )
    assert forbidden.status_code == 403

    started = pm_client.post(
        f"/api/v1/projects/{project['id']}/start-estimate",
        headers={"Authorization": "Bearer pm-token"},
        json={"version": project["version"]},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "estimating"
    assert started.json()["current_phase"] == "estimate"
    assert started.json()["version"] == 2

    stale = pm_client.post(
        f"/api/v1/projects/{project['id']}/start-estimate",
        headers={"Authorization": "Bearer pm-token"},
        json={"version": project["version"]},
    )
    assert stale.status_code == 409
