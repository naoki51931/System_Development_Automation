import uuid

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.audit import sanitize_audit_value
from app.models import AuditLog, MembershipRole, Organization, OrganizationMembership, Role, User
from app.seed import SYSTEM_ROLES, seed_system_roles


def user(sub: str, email: str, status: str = "active") -> User:
    return User(cognito_sub=sub, email=email, display_name=sub, status=status)


def test_email_is_normalized_to_lowercase(db_session: Session):
    created = user("sub-normalized", "  Person@Example.COM ")
    db_session.add(created)
    db_session.commit()

    assert created.email == "person@example.com"


@pytest.mark.parametrize("field", ["email", "cognito_sub"])
def test_user_global_identifiers_are_unique(db_session: Session, field: str):
    first = user("sub-one", "one@example.com")
    second = user("sub-two", "two@example.com")
    setattr(second, field, getattr(first, field))
    db_session.add_all([first, second])

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_user_can_have_different_roles_in_multiple_organizations(db_session: Session):
    account = user("sub-multi", "multi@example.com")
    organization_a = Organization(name="A", status="active")
    organization_b = Organization(name="B", status="active")
    admin = Role(code="organization_admin", display_name="Admin", is_system=True)
    reviewer = Role(code="reviewer", display_name="Reviewer", is_system=True)
    membership_a = OrganizationMembership(
        organization=organization_a, user=account, status="active"
    )
    membership_b = OrganizationMembership(
        organization=organization_b, user=account, status="active"
    )
    membership_a.roles.append(MembershipRole(role=admin))
    membership_b.roles.append(MembershipRole(role=reviewer))
    db_session.add_all([membership_a, membership_b])
    db_session.commit()

    assert {item.role.code for item in membership_a.roles} == {"organization_admin"}
    assert {item.role.code for item in membership_b.roles} == {"reviewer"}


def test_system_role_seed_is_idempotent(db_session: Session):
    seed_system_roles(db_session)
    db_session.commit()
    seed_system_roles(db_session)
    db_session.commit()

    assert {role.code for role in db_session.query(Role).all()} == set(SYSTEM_ROLES)


def test_audit_payload_redacts_secrets():
    sanitized = sanitize_audit_value(
        {"email": "a@example.com", "password": "plain", "nested": {"access_token": "jwt"}}
    )

    assert sanitized == {
        "email": "a@example.com",
        "password": "[REDACTED]",
        "nested": {"access_token": "[REDACTED]"},
    }


def test_audit_logs_are_append_only(db_session: Session):
    organization = Organization(name="Audit Org", status="active")
    db_session.add(organization)
    db_session.flush()
    log = AuditLog(
        organization_id=organization.id,
        action="test.created",
        resource_type="test",
        request_id=uuid.uuid4(),
        after_json={"safe": True},
    )
    db_session.add(log)
    db_session.commit()
    log.action = "changed"

    with pytest.raises(DBAPIError, match="append-only"):
        db_session.commit()
