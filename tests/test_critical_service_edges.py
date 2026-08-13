from decimal import Decimal
from datetime import date
from types import SimpleNamespace
import uuid

import pytest

from app.errors import AppError
from app.services.ai_providers import (
    AnthropicProviderStub,
    MockAIProvider,
    OpenAIProviderStub,
    AIProviderUnavailable,
)
from app.services.automation import (
    calculate_ai_cost,
    check_expected_version,
    complete_upload,
    create_upload_intent,
    update_ai_setting,
)
from app.services.billing import (
    calculate_artifact_value,
    calculate_item_amount,
    calculate_tax,
    create_estimate,
    money,
    require_roles,
    sanitize_failure,
)
from app.services.communication_providers import (
    DisabledEmailProvider,
    EmailProviderUnavailable,
    MockEmailProvider,
    MockNotificationProvider,
    NotificationProviderUnavailable,
)
from app.services.communications import (
    sanitize_plain_text,
    validate_document_payload,
    validate_internal_url,
    validate_timezone,
)
from app.services.payment_providers import (
    MockPaymentProvider,
    PaymentDeclined,
    PaymentProviderUnavailable,
    StripePaymentProviderStub,
)
from app.testing.faults import InjectedFault
from app.services.storage import (
    DEFAULT_MAX_FILE_SIZE,
    LocalArtifactStorage,
    S3ArtifactStorageStub,
)
from app.workers.outbox import heartbeat, retry_dead_letter


def test_payment_provider_full_local_contract(monkeypatch):
    provider = MockPaymentProvider(
        ["processing", "failed", "unavailable"], "webhook-local"
    )
    customer = provider.create_customer("org")
    assert customer.id.startswith("mock_cus_")
    with pytest.raises(PaymentDeclined):
        provider.attach_payment_method(customer.id, "bad")
    assert provider.attach_payment_method(customer.id, "mock_pm_local").last4 == "4242"
    intent = provider.create_payment_intent(customer.id, Decimal("10"), "JPY", "same")
    assert (
        provider.create_payment_intent(customer.id, Decimal("99"), "JPY", "same").id
        == intent.id
    )
    assert provider.confirm_payment(intent.id).status == "processing"
    assert provider.confirm_payment(intent.id).failure_code == "card_declined"
    with pytest.raises(PaymentProviderUnavailable):
        provider.confirm_payment(intent.id)
    with pytest.raises(PaymentProviderUnavailable):
        provider.confirm_payment("missing")
    assert provider.create_subscription(customer.id, "price").status == "active"
    assert (
        provider.cancel_subscription("sub").status == "cancelled"
        and provider.retry_invoice("inv") == "succeeded"
    )
    payload = b"event"
    signature = provider.sign_webhook(payload)
    assert provider.verify_webhook(payload, signature) and not provider.verify_webhook(
        payload, "bad"
    )
    with pytest.raises(PaymentProviderUnavailable):
        provider.get_payment_status("missing")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_FAULT_INJECTION", "PAYMENT_PROVIDER_UNAVAILABLE")
    with pytest.raises(InjectedFault):
        provider.confirm_payment(intent.id)
    stub = StripePaymentProviderStub()
    for call in [
        lambda: stub.create_customer("x"),
        lambda: stub.verify_webhook(b"x", "x"),
    ]:
        with pytest.raises(PaymentProviderUnavailable):
            call()


def test_communication_and_ai_providers_remain_local(monkeypatch):
    notices = MockNotificationProvider(["delivered", "unavailable"])
    result = notices.send(recipient_reference="u", title="t", body="b")
    assert (
        notices.get_status(result.provider_message_id) == "delivered"
        and notices.get_status("missing") == "unknown"
        and notices.test_connection()
    )
    with pytest.raises(NotificationProviderUnavailable):
        notices.send(recipient_reference="u", title="t", body="b")
    mail = MockEmailProvider(["delivered", "unavailable"])
    sent = mail.send_email(recipient="local@example.test", subject="s", body_text="b")
    assert (
        mail.get_delivery_status(sent.provider_message_id) == "delivered"
        and mail.get_delivery_status("missing") == "unknown"
        and mail.test_connection()
    )
    with pytest.raises(EmailProviderUnavailable):
        mail.send_email(recipient="x", subject="s", body_text="b")
    disabled = DisabledEmailProvider()
    assert not disabled.test_connection()
    with pytest.raises(EmailProviderUnavailable):
        disabled.get_delivery_status("x")
    mock = MockAIProvider([96])
    assert (
        mock.generate(b"safe", ["local"]).content.endswith(b"mock-generated")
        and mock.review(b"safe").score == 96
        and mock.revise(b"safe", ["fix"]).content != b"safe"
        and mock.test_connection()
    )
    for stub in (OpenAIProviderStub(), AnthropicProviderStub()):
        assert not stub.test_connection()
        with pytest.raises(AIProviderUnavailable):
            stub.review(b"x")


def test_billing_and_automation_reject_unsafe_edges():
    with pytest.raises(AppError):
        money(1)
    with pytest.raises(AppError):
        calculate_item_amount("option", Decimal("-1"), Decimal("1"))
    with pytest.raises(AppError):
        calculate_item_amount("discount", Decimal("1"), Decimal("1"))
    with pytest.raises(AppError):
        calculate_item_amount("option", Decimal("1"), Decimal("-1"))
    with pytest.raises(AppError):
        calculate_tax(Decimal("-1"))
    with pytest.raises(AppError):
        calculate_artifact_value(
            Decimal("1"), Decimal("1"), Decimal("1"), screen_count=-1
        )
    assert "[REDACTED]" in sanitize_failure("api_key=secret")
    denied = SimpleNamespace(role_codes=frozenset({"viewer"}))
    with pytest.raises(AppError):
        require_roles(denied, frozenset({"owner"}))
    with pytest.raises(AppError):
        calculate_ai_cost(-1, 0, 0, Decimal("1"), Decimal("1"), Decimal("1"))
    resource = SimpleNamespace(version=2)
    with pytest.raises(AppError):
        check_expected_version(resource, 1)
    setting = SimpleNamespace(version=1)
    with pytest.raises(AppError):
        update_ai_setting(
            SimpleNamespace(flush=lambda: None), setting, 1, {"provider": "external"}
        )


def test_communications_reject_invalid_snapshot_inputs():
    """Exercise fail-closed validation used before resumable document side effects."""
    assert validate_internal_url(None) is None
    with pytest.raises(AppError, match="internal relative URL"):
        validate_internal_url("https://external.example.test/document")
    with pytest.raises(AppError, match="valid IANA"):
        validate_timezone("Not/A_Timezone")
    with pytest.raises(AppError, match="Message body is invalid"):
        sanitize_plain_text("<script>ignored()</script>")

    schema = {
        "type": "object",
        "properties": {"title": {"type": "string"}},
        "required": ["title"],
        "additionalProperties": False,
    }
    for payload, message in (
        ({}, "Required document fields are missing"),
        ({"title": "safe", "unexpected": True}, "Unknown document fields"),
        ({"title": 1}, "Document field type is invalid"),
        ({"title": "https://external.example.test"}, "External document references"),
    ):
        with pytest.raises(AppError, match=message):
            validate_document_payload(schema, payload)


def test_heartbeat_rejects_wrong_owner():
    job = SimpleNamespace(status="processing", locked_by="worker-a")
    assert heartbeat(SimpleNamespace(), job, "worker-b") is False
    job.status = "completed"
    assert heartbeat(SimpleNamespace(), job, "worker-a") is False


def test_upload_intent_and_completion_are_tenant_bound(db_session, tmp_path):
    from tests.test_ai_storage_workflow import make_context

    organization, user, access, _project, artifact = make_context(db_session)
    storage = LocalArtifactStorage(tmp_path)
    content = b"immutable upload"
    import hashlib

    digest = hashlib.sha256(content).hexdigest()
    intent, upload_url = create_upload_intent(
        db_session,
        storage,
        artifact,
        access,
        filename="evidence.md",
        mime_type="text/markdown",
        file_size=len(content),
        content_hash=digest,
    )
    assert upload_url.startswith("local-upload://")
    storage.put_object(intent.storage_key, content, "text/markdown")
    version = complete_upload(db_session, storage, intent, artifact, access)
    assert version.id == intent.version_id
    assert artifact.current_version_id == version.id
    assert intent.status == "completed"
    assert storage.create_download_url(intent.storage_key).startswith(
        "local-download://"
    )
    assert organization.id == artifact.organization_id and user.id == access.user.id


def test_upload_validation_fails_before_side_effects(db_session, tmp_path):
    from tests.test_ai_storage_workflow import make_context

    _organization, _user, access, _project, artifact = make_context(db_session)
    storage = LocalArtifactStorage(tmp_path, max_file_size=4)
    cases = [
        {"mime_type": "text/html", "file_size": 1, "content_hash": "a" * 64},
        {
            "mime_type": "text/plain",
            "file_size": DEFAULT_MAX_FILE_SIZE + 1,
            "content_hash": "a" * 64,
        },
        {"mime_type": "text/plain", "file_size": 1, "content_hash": "invalid"},
    ]
    for values in cases:
        with pytest.raises(AppError):
            create_upload_intent(
                db_session,
                storage,
                artifact,
                access,
                filename="safe.txt",
                **values,
            )
    denied = type(access)(access.user, access.membership, frozenset({"viewer"}))
    with pytest.raises(AppError, match="Permission denied"):
        create_upload_intent(
            db_session,
            storage,
            artifact,
            denied,
            filename="safe.txt",
            mime_type="text/plain",
            file_size=1,
            content_hash="a" * 64,
        )


def test_storage_missing_delete_and_disabled_provider(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    ids = [uuid.uuid4() for _ in range(4)]
    with pytest.raises(AppError):
        storage.build_storage_key(*ids, "...")
    key = storage.build_storage_key(*ids, "temporary.txt")
    with pytest.raises(AppError, match="not found"):
        storage.get_object(key)
    storage.put_object(key, b"temporary", "text/plain")
    storage.delete_unapproved_object(key, approved=False)
    with pytest.raises(AppError, match="not found"):
        storage.head_object(key)
    with pytest.raises(AppError, match="disabled"):
        S3ArtifactStorageStub().get_object(key)


def test_owned_heartbeat_and_manual_retry_guards():
    session = SimpleNamespace(flush=lambda: None)
    job = SimpleNamespace(status="processing", locked_by="worker-a")
    assert heartbeat(session, job, "worker-a", lease_seconds=5)
    assert job.heartbeat_at is not None and job.lease_expires_at > job.heartbeat_at
    with pytest.raises(ValueError, match="dead-lettered"):
        retry_dead_letter(session, SimpleNamespace(status="completed"))
    dead = SimpleNamespace(
        status="dead_letter",
        attempt_count=3,
        dead_lettered_at=job.heartbeat_at,
        available_at=None,
        last_error_code="safe-code",
    )
    retry_dead_letter(session, dead)
    assert dead.status == "queued" and dead.attempt_count == 0


def test_estimate_snapshots_completed_ai_and_artifact_value(db_session):
    from app.models.billing import ArtifactPricingSnapshot, EstimateItem
    from app.models.project import AIRun
    from tests.test_ai_storage_workflow import make_context
    from sqlalchemy import select

    organization, _user, access, project, artifact = make_context(db_session)
    run = AIRun(
        organization_id=organization.id,
        project_id=project.id,
        provider="openai",
        model="mock-v1",
        operation_type="revision",
        status="completed",
        calculated_cost=Decimal("12.5"),
        retry_count=0,
    )
    db_session.add(run)
    db_session.flush()
    estimate = create_estimate(
        db_session,
        project,
        access,
        estimate_number=f"EST-{uuid.uuid4().hex[:8]}",
        valid_until=date.today(),
        include_ai_runs=True,
        include_artifacts=True,
    )
    items = db_session.scalars(
        select(EstimateItem).where(EstimateItem.estimate_id == estimate.id)
    ).all()
    assert {item.source_type for item in items} == {"ai_run", "artifact"}
    artifact_item = next(item for item in items if item.source_type == "artifact")
    snapshot = db_session.scalar(
        select(ArtifactPricingSnapshot).where(
            ArtifactPricingSnapshot.estimate_item_id == artifact_item.id
        )
    )
    assert snapshot is not None and snapshot.artifact_id == artifact.id
    # Re-running collectors is idempotent for both source identities.
    from app.services.billing import (
        generate_ai_run_items,
        generate_artifact_value_items,
    )

    generate_ai_run_items(db_session, estimate)
    generate_artifact_value_items(db_session, estimate)
    assert (
        len(
            db_session.scalars(
                select(EstimateItem).where(EstimateItem.estimate_id == estimate.id)
            ).all()
        )
        == 2
    )
