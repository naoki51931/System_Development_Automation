import hashlib
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, require_organization_access
from app.errors import AppError
from app.models import MembershipRole, Organization, OrganizationMembership, Role, User
from app.models.communications import (
    ChangeRequestImpact,
    EmailMessage,
    EmailTemplate,
    NotificationDelivery,
    NotificationPreference,
)
from app.models.project import ArtifactVersion, ProjectMember
from app.services.ai_providers import MockAIProvider
from app.services.billing import (
    accept_contract,
    create_contract,
    create_estimate,
    transition_estimate,
)
from app.services.communication_providers import (
    MockEmailProvider,
    MockNotificationProvider,
    SESEmailProviderStub,
    EmailProviderUnavailable,
)
from app.services.communications import (
    analyze_change_request,
    attach_chat_artifact,
    create_change_request,
    create_chat_room,
    create_email_message,
    create_notification,
    decide_change_request,
    delete_chat_message,
    deliver_notification,
    edit_chat_message,
    enqueue_outbox_event,
    generate_document,
    mark_notification_read,
    post_ai_chat_message,
    post_chat_message,
    process_outbox_event,
    render_template,
    resolve_email_template,
    sanitize_plain_text,
    scheduled_delivery_time,
    send_email_message,
    update_preference,
)
from app.services.storage import LocalArtifactStorage
from app.services.workflow import create_artifact, create_project


def context(session: Session, suffix: str = "comms"):
    organization = Organization(name=f"Org {suffix}", status="active")
    user = User(
        cognito_sub=f"sub-{suffix}-{uuid.uuid4()}",
        email=f"{uuid.uuid4()}@example.com",
        display_name=suffix,
        status="active",
    )
    role = Role(
        code=f"comms-{uuid.uuid4().hex[:20]}",
        display_name="Comms Admin",
        is_system=False,
    )
    membership = OrganizationMembership(
        organization=organization, user=user, status="active"
    )
    membership.roles.append(MembershipRole(role=role))
    session.add(membership)
    session.flush()
    raw = require_organization_access(organization.id, AuthenticatedUser(user), session)
    access = type(raw)(
        raw.user,
        raw.membership,
        frozenset({"organization_admin", "customer", "reviewer"}),
    )
    project = create_project(
        session,
        access,
        project_code=f"P-{uuid.uuid4().hex[:10]}",
        name="Communication Project",
        description="Local only",
        status="draft",
        current_phase="estimate",
        customer_user_id=user.id,
        project_manager_user_id=user.id,
    )
    session.add(
        ProjectMember(
            project_id=project.id,
            user_id=user.id,
            project_role="project_manager",
            status="active",
        )
    )
    session.flush()
    return organization, user, access, project


def approved_estimate(session: Session):
    organization, user, access, project = context(session, "estimate-doc")
    estimate = create_estimate(
        session,
        project,
        access,
        estimate_number=f"E-{uuid.uuid4().hex[:8]}",
        valid_until=date.today() + timedelta(days=30),
        include_ai_runs=False,
        include_artifacts=False,
        items=[
            {
                "item_type": "option",
                "description": "Build",
                "quantity": Decimal("2"),
                "unit": "day",
                "unit_price": Decimal("100"),
            }
        ],
    )
    transition_estimate(session, estimate, access, "submit", estimate.version)
    transition_estimate(session, estimate, access, "approve", estimate.version)
    return organization, user, access, project, estimate


def test_notification_creation_dedup_read_critical_audit(db_session: Session):
    organization, user, access, project = context(db_session, "notification")
    item = create_notification(
        db_session,
        organization_id=organization.id,
        user_id=user.id,
        project_id=project.id,
        event_type="payment_failed",
        title="Payment failed",
        body="api_key=secret",
        severity="critical",
        action_url="/payments/1",
        deduplication_key="payment:1",
    )
    assert "[REDACTED]" in item.body
    assert db_session.query(NotificationDelivery).count() == 1
    with pytest.raises(AppError) as duplicate:
        create_notification(
            db_session,
            organization_id=organization.id,
            user_id=user.id,
            project_id=project.id,
            event_type="payment_failed",
            title="Again",
            body="Again",
            severity="critical",
            action_url="/",
            deduplication_key="payment:1",
        )
    assert duplicate.value.code == "DUPLICATE_NOTIFICATION"
    mark_notification_read(db_session, item, access, item.version)
    assert item.status == "read" and item.read_at is not None
    with pytest.raises(AppError) as conflict:
        mark_notification_read(db_session, item, access, 1)
    assert conflict.value.code == "VERSION_CONFLICT"


def test_notification_internal_url_and_other_org_rejected(db_session: Session):
    organization, user, _access, project = context(db_session, "url")
    with pytest.raises(AppError):
        create_notification(
            db_session,
            organization_id=organization.id,
            user_id=user.id,
            project_id=project.id,
            event_type="x",
            title="x",
            body="x",
            severity="info",
            action_url="https://evil.example",
            deduplication_key="x",
        )
    _other_org, _other_user, other_access, _other_project = context(db_session, "other")
    item = create_notification(
        db_session,
        organization_id=organization.id,
        user_id=user.id,
        project_id=project.id,
        event_type="x",
        title="x",
        body="x",
        severity="info",
        action_url="/x",
        deduplication_key="y",
    )
    with pytest.raises(HTTPException):
        mark_notification_read(db_session, item, other_access, item.version)


def test_quiet_hours_digest_and_security_override(db_session: Session):
    organization, user, access, _project = context(db_session, "quiet")
    preference = NotificationPreference(
        organization_id=organization.id,
        user_id=user.id,
        event_type="chat_message_received",
        in_app_enabled=True,
        email_enabled=True,
        digest_mode="immediate",
        quiet_hours_start=time(22, 0),
        quiet_hours_end=time(7, 0),
        timezone="Asia/Tokyo",
    )
    db_session.add(preference)
    db_session.flush()
    now = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
    scheduled = scheduled_delivery_time(preference, now, "info")
    assert scheduled == datetime(2026, 1, 1, 22, 0, tzinfo=timezone.utc)
    preference.event_type = "maintenance_suspended"
    update_preference(
        db_session,
        preference,
        access,
        preference.version,
        {"in_app_enabled": False, "digest_mode": "none"},
    )
    assert preference.in_app_enabled is True
    assert preference.digest_mode == "immediate"


def test_notification_delivery_retry_backoff(db_session: Session):
    organization, user, _access, project = context(db_session, "retry")
    item = create_notification(
        db_session,
        organization_id=organization.id,
        user_id=user.id,
        project_id=project.id,
        event_type="x",
        title="x",
        body="x",
        severity="info",
        action_url="/x",
        deduplication_key="retry",
    )
    delivery = db_session.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.notification_id == item.id
        )
    )
    assert delivery is not None
    now = delivery.scheduled_at
    deliver_notification(
        db_session, delivery, MockNotificationProvider(["unavailable"]), now
    )
    assert delivery.status == "failed"
    assert delivery.attempt_count == 1
    assert delivery.scheduled_at > now


def approved_template(session: Session, organization_id=None, code="estimate_approved"):
    template = EmailTemplate(
        organization_id=organization_id,
        template_code=code,
        name=code,
        subject_template="{{ service_name }} notification",
        body_text_template="Hello {{ user_name }} {{ download_url }}",
        body_html_template="<p>Hello {{ user_name }}</p><script>alert(1)</script>",
        locale="ja",
        status="approved",
        version_number=1,
    )
    session.add(template)
    session.flush()
    return template


def test_email_template_resolution_render_sanitize_and_variables(db_session: Session):
    organization, _user, _access, _project = context(db_session, "template")
    system = approved_template(db_session)
    tenant = approved_template(db_session, organization.id)
    assert (
        resolve_email_template(db_session, organization.id, "estimate_approved").id
        == tenant.id
    )
    rendered = render_template(
        tenant.body_html_template or "", {"user_name": "<b>A</b>"}, html_output=True
    )
    assert "<script" not in rendered.lower()
    assert "&lt;b&gt;" in rendered
    with pytest.raises(AppError):
        render_template("{{ forbidden }}", {})
    with pytest.raises(AppError):
        render_template(
            "{{ service_name }}", {"service_name": "x", "password": "secret"}
        )
    assert system.id != tenant.id


def test_email_snapshot_idempotency_success_failure_and_no_external(
    db_session: Session,
):
    organization, user, _access, project = context(db_session, "email")
    template = approved_template(db_session, organization.id, "document")
    values = {
        "service_name": "SystemNavigator AI",
        "user_name": user.display_name,
        "download_url": "local-download://opaque",
    }
    message = create_email_message(
        db_session,
        template,
        user,
        organization_id=organization.id,
        project_id=project.id,
        notification_id=None,
        values=values,
        deduplication_key="email:one",
        scheduled_at=datetime.now(timezone.utc),
    )
    same = create_email_message(
        db_session,
        template,
        user,
        organization_id=organization.id,
        project_id=project.id,
        notification_id=None,
        values=values,
        deduplication_key="email:one",
        scheduled_at=datetime.now(timezone.utc),
    )
    assert same.id == message.id
    send_email_message(
        db_session,
        message,
        MockEmailProvider(["delivered"]),
        datetime.now(timezone.utc),
    )
    assert message.status == "delivered"
    assert db_session.query(EmailMessage).count() == 1
    assert "bcc" not in EmailMessage.__table__.columns
    with pytest.raises(EmailProviderUnavailable):
        SESEmailProviderStub().send_email(
            recipient=user.email, subject="x", body_text="x"
        )


def test_email_header_injection_rejected(db_session: Session):
    organization, user, _access, project = context(db_session, "header")
    template = EmailTemplate(
        organization_id=organization.id,
        template_code="bad",
        name="bad",
        subject_template="Subject\r\nBcc: victim@example.com",
        body_text_template="Body",
        locale="ja",
        status="approved",
        version_number=1,
    )
    db_session.add(template)
    db_session.flush()
    with pytest.raises(AppError) as error:
        create_email_message(
            db_session,
            template,
            user,
            organization_id=organization.id,
            project_id=project.id,
            notification_id=None,
            values={},
            deduplication_key="bad:header",
            scheduled_at=datetime.now(timezone.utc),
        )
    assert error.value.code == "INVALID_TEMPLATE_DATA"


@pytest.mark.parametrize("output_format", ["pdf", "html", "markdown"])
def test_estimate_document_generation_hash_and_idempotency(
    db_session: Session, tmp_path, output_format: str
):
    _organization, _user, access, project, estimate = approved_estimate(db_session)
    storage = LocalArtifactStorage(tmp_path)
    job = generate_document(
        db_session,
        storage,
        project,
        access,
        document_type="estimate",
        output_format=output_format,
        source_id=estimate.id,
    )
    assert job.status == "completed"
    content = storage.get_object(job.storage_key or "")
    assert hashlib.sha256(content).hexdigest() == job.content_hash
    assert job.file_size == len(content)
    if output_format == "pdf":
        assert content.startswith(b"%PDF")
        assert b"api_key" not in content
    with pytest.raises(AppError) as duplicate:
        generate_document(
            db_session,
            storage,
            project,
            access,
            document_type="estimate",
            output_format=output_format,
            source_id=estimate.id,
        )
    assert duplicate.value.code == "DOCUMENT_ALREADY_GENERATED"


def test_contract_and_basic_design_documents_use_authoritative_data(
    db_session: Session, tmp_path
):
    organization, user, access, project, estimate = approved_estimate(db_session)
    contract = create_contract(
        db_session,
        estimate,
        project,
        access,
        contract_number=f"C-{uuid.uuid4().hex[:8]}",
        contract_type="development",
        terms_version="terms-v1",
    )
    accept_contract(
        db_session,
        contract,
        access,
        party="customer",
        expected_version=contract.version,
        request_id=uuid.uuid4(),
    )
    accept_contract(
        db_session,
        contract,
        access,
        party="provider",
        expected_version=contract.version,
        request_id=uuid.uuid4(),
    )
    storage = LocalArtifactStorage(tmp_path)
    contract_job = generate_document(
        db_session,
        storage,
        project,
        access,
        document_type="contract",
        output_format="markdown",
        source_id=contract.id,
    )
    contract_text = storage.get_object(contract_job.storage_key or "").decode()
    assert str(estimate.total_amount) in contract_text
    assert contract.contract_number in contract_text
    design_job = generate_document(
        db_session,
        storage,
        project,
        access,
        document_type="basic_design",
        output_format="markdown",
    )
    design_text = storage.get_object(design_job.storage_key or "").decode()
    assert "未設定" in design_text
    assert organization.name not in design_text or organization.name == "未設定"


def test_unapproved_estimate_document_rejected(db_session: Session, tmp_path):
    organization, user, access, project = context(db_session, "unapproved-doc")
    estimate = create_estimate(
        db_session,
        project,
        access,
        estimate_number="E-DRAFT",
        valid_until=date.today() + timedelta(days=10),
        include_ai_runs=False,
        include_artifacts=False,
    )
    with pytest.raises(AppError):
        generate_document(
            db_session,
            LocalArtifactStorage(tmp_path),
            project,
            access,
            document_type="estimate",
            output_format="pdf",
            source_id=estimate.id,
        )


def test_chat_post_edit_delete_xss_and_ai_identity(db_session: Session):
    _organization, user, access, project = context(db_session, "chat")
    room = create_chat_room(
        db_session, project, access, room_type="project", name="General"
    )
    message = post_chat_message(
        db_session,
        room,
        project,
        access,
        body="<script>alert(1)</script>Hello",
        message_type="user",
    )
    assert "<script" not in message.body
    assert message.sender_user_id == user.id
    edit_chat_message(db_session, message, access, "Edited", message.version)
    assert message.status == "edited"
    delete_chat_message(db_session, message, access, message.version)
    assert message.status == "deleted" and message.body == "[deleted]"
    ai_message = post_ai_chat_message(db_session, room, "AI analysis")
    assert ai_message.message_type == "ai" and ai_message.sender_user_id is None
    with pytest.raises(AppError):
        post_chat_message(
            db_session, room, project, access, body="fake", message_type="ai"
        )


@pytest.mark.parametrize("room_status", ["archived", "closed"])
def test_inactive_chat_room_rejects_post(db_session: Session, room_status: str):
    _organization, _user, access, project = context(db_session, f"room-{room_status}")
    room = create_chat_room(
        db_session, project, access, room_type="project", name="General"
    )
    room.status = room_status
    with pytest.raises(AppError) as error:
        post_chat_message(db_session, room, project, access, body="No")
    assert error.value.code == "INVALID_CHAT_STATE"


def test_other_organization_chat_access_rejected(db_session: Session):
    _organization, _user, access, project = context(db_session, "chat-one")
    room = create_chat_room(
        db_session, project, access, room_type="project", name="General"
    )
    _other_org, _other_user, other_access, _other_project = context(
        db_session, "chat-two"
    )
    with pytest.raises(HTTPException):
        post_chat_message(db_session, room, project, other_access, body="No")


def test_chat_attachment_validates_storage_scope_hash_and_mime(
    db_session: Session, tmp_path
):
    organization, user, access, project = context(db_session, "attachment")
    room = create_chat_room(
        db_session, project, access, room_type="project", name="Files"
    )
    message = post_chat_message(db_session, room, project, access, body="File")
    artifact = create_artifact(
        db_session,
        project,
        access,
        artifact_type="basic_design",
        title="File",
        status="draft",
        created_by_user_id=user.id,
    )
    storage = LocalArtifactStorage(tmp_path)
    version_id = uuid.uuid4()
    key = storage.build_storage_key(
        organization.id, project.id, artifact.id, version_id, "file.md"
    )
    metadata = storage.put_object(key, b"safe", "text/markdown")
    version = ArtifactVersion(
        id=version_id,
        artifact_id=artifact.id,
        version_number=1,
        storage_key=key,
        content_hash=metadata.content_hash,
        mime_type=metadata.mime_type,
        file_size=metadata.size,
        generated_by="human",
        created_by_user_id=user.id,
    )
    db_session.add(version)
    db_session.flush()
    attachment = attach_chat_artifact(
        db_session, storage, message, version, artifact, access, "../file.md"
    )
    assert attachment.filename == "file.md"
    version.content_hash = "0" * 64
    with pytest.raises(AppError):
        attach_chat_artifact(
            db_session, storage, message, version, artifact, access, "bad.md"
        )


def test_change_request_mock_analysis_human_approval_and_estimate_link(
    db_session: Session,
):
    _organization, user, access, project, estimate = approved_estimate(db_session)
    room = create_chat_room(
        db_session, project, access, room_type="project", name="Changes"
    )
    message = post_chat_message(db_session, room, project, access, body="Add feature")
    request = create_change_request(
        db_session,
        message,
        access,
        title="Feature",
        description="Add a new feature",
        priority="high",
        scope_type="major_change",
        estimate_id=estimate.id,
    )
    assert request.status == "draft"
    analyze_change_request(
        db_session, request, access, MockAIProvider([75]), request.version
    )
    assert request.status == "awaiting_customer_approval"
    assert (
        db_session.query(ChangeRequestImpact)
        .filter_by(change_request_id=request.id)
        .count()
        == 1
    )
    assert request.approved_by_user_id is None
    decide_change_request(db_session, request, access, "approve", request.version)
    assert request.status == "approved" and request.approved_by_user_id == user.id
    assert request.estimate_id == estimate.id


def test_change_request_other_org_approval_rejected(db_session: Session):
    _organization, _user, access, project = context(db_session, "change-one")
    room = create_chat_room(
        db_session, project, access, room_type="project", name="Changes"
    )
    message = post_chat_message(db_session, room, project, access, body="Change")
    request = create_change_request(
        db_session,
        message,
        access,
        title="Change",
        description="Change",
        priority="normal",
        scope_type="minor_change",
    )
    analyze_change_request(
        db_session, request, access, MockAIProvider([80]), request.version
    )
    _other_org, _other_user, other_access, _other_project = context(
        db_session, "change-two"
    )
    with pytest.raises(HTTPException):
        decide_change_request(
            db_session, request, other_access, "approve", request.version
        )


def test_outbox_dedup_retry_and_processed_noop(db_session: Session):
    organization, _user, _access, project = context(db_session, "outbox")
    event = enqueue_outbox_event(
        db_session,
        organization_id=organization.id,
        event_type="document_generated",
        aggregate_type="project",
        aggregate_id=project.id,
        payload={"x": 1},
    )
    same = enqueue_outbox_event(
        db_session,
        organization_id=organization.id,
        event_type="document_generated",
        aggregate_type="project",
        aggregate_id=project.id,
        payload={"x": 1},
    )
    assert same.id == event.id
    now = datetime.now(timezone.utc)
    process_outbox_event(
        db_session,
        event,
        lambda _event: (_ for _ in ()).throw(RuntimeError("fail")),
        now,
    )
    assert (
        event.status == "failed"
        and event.attempt_count == 1
        and event.available_at > now
    )
    event.available_at = now
    calls = []
    process_outbox_event(db_session, event, lambda value: calls.append(value.id), now)
    assert event.status == "processed" and calls == [event.id]
    process_outbox_event(db_session, event, lambda value: calls.append(value.id), now)
    assert calls == [event.id]


def test_no_external_references_or_secrets_in_templates():
    with pytest.raises(AppError):
        render_template('<img src="https://evil.example/x">', {})
    assert "[REDACTED]" in sanitize_plain_text("token=secret safe")
