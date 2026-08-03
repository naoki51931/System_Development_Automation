from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.errors import AppError
from app.services.ai_providers import AnthropicProviderStub, MockAIProvider, OpenAIProviderStub, AIProviderUnavailable
from app.services.automation import calculate_ai_cost, check_expected_version, update_ai_setting
from app.services.billing import calculate_artifact_value, calculate_item_amount, calculate_tax, money, require_roles, sanitize_failure
from app.services.communication_providers import DisabledEmailProvider, EmailProviderUnavailable, MockEmailProvider, MockNotificationProvider, NotificationProviderUnavailable
from app.services.payment_providers import MockPaymentProvider, PaymentDeclined, PaymentProviderUnavailable, StripePaymentProviderStub
from app.testing.faults import InjectedFault
from app.workers.outbox import heartbeat


def test_payment_provider_full_local_contract(monkeypatch):
    provider=MockPaymentProvider(["processing","failed","unavailable"],"webhook-local")
    customer=provider.create_customer("org"); assert customer.id.startswith("mock_cus_")
    with pytest.raises(PaymentDeclined): provider.attach_payment_method(customer.id,"bad")
    assert provider.attach_payment_method(customer.id,"mock_pm_local").last4=="4242"
    intent=provider.create_payment_intent(customer.id,Decimal("10"),"JPY","same")
    assert provider.create_payment_intent(customer.id,Decimal("99"),"JPY","same").id==intent.id
    assert provider.confirm_payment(intent.id).status=="processing"
    assert provider.confirm_payment(intent.id).failure_code=="card_declined"
    with pytest.raises(PaymentProviderUnavailable): provider.confirm_payment(intent.id)
    with pytest.raises(PaymentProviderUnavailable): provider.confirm_payment("missing")
    assert provider.create_subscription(customer.id,"price").status=="active"
    assert provider.cancel_subscription("sub").status=="cancelled" and provider.retry_invoice("inv")=="succeeded"
    payload=b"event"; signature=provider.sign_webhook(payload); assert provider.verify_webhook(payload,signature) and not provider.verify_webhook(payload,"bad")
    with pytest.raises(PaymentProviderUnavailable): provider.get_payment_status("missing")
    monkeypatch.setenv("APP_ENV","test");monkeypatch.setenv("APP_FAULT_INJECTION","PAYMENT_PROVIDER_UNAVAILABLE")
    with pytest.raises(InjectedFault): provider.confirm_payment(intent.id)
    stub=StripePaymentProviderStub()
    for call in [lambda:stub.create_customer("x"),lambda:stub.verify_webhook(b"x","x")]:
        with pytest.raises(PaymentProviderUnavailable):call()


def test_communication_and_ai_providers_remain_local(monkeypatch):
    notices=MockNotificationProvider(["delivered","unavailable"]); result=notices.send(recipient_reference="u",title="t",body="b")
    assert notices.get_status(result.provider_message_id)=="delivered" and notices.get_status("missing")=="unknown" and notices.test_connection()
    with pytest.raises(NotificationProviderUnavailable):notices.send(recipient_reference="u",title="t",body="b")
    mail=MockEmailProvider(["delivered","unavailable"]); sent=mail.send_email(recipient="local@example.test",subject="s",body_text="b")
    assert mail.get_delivery_status(sent.provider_message_id)=="delivered" and mail.get_delivery_status("missing")=="unknown" and mail.test_connection()
    with pytest.raises(EmailProviderUnavailable):mail.send_email(recipient="x",subject="s",body_text="b")
    disabled=DisabledEmailProvider();assert not disabled.test_connection()
    with pytest.raises(EmailProviderUnavailable):disabled.get_delivery_status("x")
    mock=MockAIProvider([96]); assert mock.generate(b"safe",["local"]).content.endswith(b"mock-generated") and mock.review(b"safe").score==96 and mock.revise(b"safe",["fix"]).content!=b"safe" and mock.test_connection()
    for stub in (OpenAIProviderStub(),AnthropicProviderStub()):
        assert not stub.test_connection()
        with pytest.raises(AIProviderUnavailable):stub.review(b"x")


def test_billing_and_automation_reject_unsafe_edges():
    with pytest.raises(AppError):money(1)
    with pytest.raises(AppError):calculate_item_amount("option",Decimal("-1"),Decimal("1"))
    with pytest.raises(AppError):calculate_item_amount("discount",Decimal("1"),Decimal("1"))
    with pytest.raises(AppError):calculate_item_amount("option",Decimal("1"),Decimal("-1"))
    with pytest.raises(AppError):calculate_tax(Decimal("-1"))
    with pytest.raises(AppError):calculate_artifact_value(Decimal("1"),Decimal("1"),Decimal("1"),screen_count=-1)
    assert "[REDACTED]" in sanitize_failure("api_key=secret")
    denied=SimpleNamespace(role_codes=frozenset({"viewer"}))
    with pytest.raises(AppError):require_roles(denied,frozenset({"owner"}))
    with pytest.raises(AppError):calculate_ai_cost(-1,0,0,Decimal("1"),Decimal("1"),Decimal("1"))
    resource=SimpleNamespace(version=2)
    with pytest.raises(AppError):check_expected_version(resource,1)
    setting=SimpleNamespace(version=1)
    with pytest.raises(AppError):update_ai_setting(SimpleNamespace(flush=lambda:None),setting,1,{"provider":"external"})


def test_heartbeat_rejects_wrong_owner():
    job=SimpleNamespace(status="processing",locked_by="worker-a")
    assert heartbeat(SimpleNamespace(),job,"worker-b") is False
    job.status="completed";assert heartbeat(SimpleNamespace(),job,"worker-a") is False
