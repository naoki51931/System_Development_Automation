import os, uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy.orm import Session
from app.api.pagination import decode_cursor, encode_cursor
from app.auth.verifier import LocalAuthProvider, TokenVerificationError
from app.models import Organization, OutboxEvent
from app.workers.outbox import claim, complete, fail, retry_dead_letter

NOW=lambda: datetime.now(timezone.utc)
def event(session: Session, *, attempts=0, maximum=3, status="queued", lease=None):
    org=Organization(name=f"worker-{uuid.uuid4()}"); session.add(org); session.flush()
    item=OutboxEvent(organization_id=org.id,event_type="test",aggregate_type="project",aggregate_id=uuid.uuid4(),payload_hash=uuid.uuid4().hex.ljust(64,"0"),status=status,attempt_count=attempts,max_attempts=maximum,available_at=NOW()-timedelta(seconds=1),lease_expires_at=lease)
    session.add(item);session.flush();return item

def test_signed_cursor_rejects_tampering():
    value=encode_cursor(NOW(),uuid.uuid4()); assert decode_cursor(value)
    with pytest.raises(Exception): decode_cursor(value[:-2]+"xx")

def test_local_token_contains_subject_not_roles():
    provider=LocalAuthProvider("test-secret"); raw=provider.issue("subject"); verified=provider.verify(raw)
    assert verified.subject=="subject" and "organization_id" not in verified.claims and "role" not in verified.claims

def test_worker_claim_complete_and_idempotent_completed_not_reclaimed(db_session):
    item=event(db_session); claimed=claim(db_session,"worker-a",30); assert claimed.id==item.id and claimed.status=="processing" and claimed.attempt_count==1
    complete(db_session,claimed); db_session.flush(); assert claim(db_session,"worker-b") is None

def test_expired_lease_is_reclaimed(db_session):
    item=event(db_session,status="processing",lease=NOW()-timedelta(seconds=1)); item.locked_by="dead-worker"
    claimed=claim(db_session,"worker-b"); assert claimed.id==item.id and claimed.locked_by=="worker-b"

def test_retry_then_dead_letter_and_manual_retry(db_session, monkeypatch):
    item=event(db_session,maximum=2); claim(db_session,"worker",30); fail(db_session,item,"TEMPORARY"); assert item.status=="retry_wait"
    item.available_at=NOW()-timedelta(seconds=1); claim(db_session,"worker",30); fail(db_session,item,"POISON"); assert item.status=="dead_letter" and item.dead_lettered_at
    retry_dead_letter(db_session,item); assert item.status=="queued" and item.attempt_count==0

def test_last_owner_cannot_remove_self(db_session):
    from fastapi import HTTPException
    from app.api.admin import ensure_last_owner
    from app.models import MembershipRole, OrganizationMembership, Role, User
    org=Organization(name="owner-org"); user=User(cognito_sub="owner",email="owner@example.test",display_name="Owner"); role=Role(code="organization_owner",display_name="Owner")
    db_session.add_all([org,user,role]);db_session.flush(); membership=OrganizationMembership(organization_id=org.id,user_id=user.id,status="active");db_session.add(membership);db_session.flush();membership.roles.append(MembershipRole(role=role));db_session.flush()
    with pytest.raises(HTTPException) as exc: ensure_last_owner(db_session,membership,user.id,set())
    assert exc.value.status_code==409 and exc.value.detail["code"]=="LAST_ORGANIZATION_OWNER"

def test_local_auth_is_disabled_in_production(monkeypatch):
    from fastapi import HTTPException
    from app.api.local_auth import enabled
    from app.core.config import get_settings
    monkeypatch.setenv("APP_ENV","production");monkeypatch.setenv("APP_LOCAL_AUTH_ENABLED","true");get_settings.cache_clear()
    with pytest.raises(HTTPException) as exc: enabled()
    assert exc.value.status_code==404
    get_settings.cache_clear()
