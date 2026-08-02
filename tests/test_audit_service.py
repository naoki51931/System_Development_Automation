import uuid

from sqlalchemy.orm import Session

from app.audit import record_audit_log
from app.models import Organization


def test_record_audit_log_never_persists_secrets(db_session: Session):
    organization = Organization(name="Safe Audit", status="active")
    db_session.add(organization)
    db_session.flush()

    log = record_audit_log(
        db_session,
        organization_id=organization.id,
        action="security.tested",
        resource_type="test",
        request_id=uuid.uuid4(),
        before={"password": "before-secret"},
        after={"nested": {"client_secret": "after-secret"}, "safe": "visible"},
    )
    db_session.commit()

    assert log.before_json == {"password": "[REDACTED]"}
    assert log.after_json == {
        "nested": {"client_secret": "[REDACTED]"},
        "safe": "visible",
    }
