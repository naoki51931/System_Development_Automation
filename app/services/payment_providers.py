import hashlib
import hmac
import secrets
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from app.testing.faults import inject


class PaymentProviderError(Exception):
    pass


class PaymentProviderUnavailable(PaymentProviderError):
    pass


class PaymentAuthenticationError(PaymentProviderError):
    pass


class PaymentDeclined(PaymentProviderError):
    def __init__(self, code: str = "card_declined", message: str = "Payment was declined"):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ProviderCustomer:
    id: str


@dataclass(frozen=True)
class ProviderPaymentMethod:
    id: str
    brand: str
    last4: str
    expiry_month: int
    expiry_year: int


@dataclass(frozen=True)
class ProviderPaymentIntent:
    id: str
    status: str
    amount: Decimal
    currency: str
    failure_code: str | None = None
    failure_message: str | None = None


@dataclass(frozen=True)
class ProviderSubscription:
    id: str
    status: str


class PaymentProvider(ABC):
    @abstractmethod
    def create_customer(self, organization_reference: str) -> ProviderCustomer: ...
    @abstractmethod
    def attach_payment_method(self, customer_id: str, payment_method_token: str) -> ProviderPaymentMethod: ...
    @abstractmethod
    def create_payment_intent(self, customer_id: str | None, amount: Decimal, currency: str, idempotency_key: str) -> ProviderPaymentIntent: ...
    @abstractmethod
    def confirm_payment(self, payment_intent_id: str) -> ProviderPaymentIntent: ...
    @abstractmethod
    def create_subscription(self, customer_id: str, price_reference: str) -> ProviderSubscription: ...
    @abstractmethod
    def cancel_subscription(self, subscription_id: str) -> ProviderSubscription: ...
    @abstractmethod
    def retry_invoice(self, invoice_id: str) -> str: ...
    @abstractmethod
    def verify_webhook(self, payload: bytes, signature: str) -> bool: ...
    @abstractmethod
    def get_payment_status(self, payment_intent_id: str) -> str: ...


class MockPaymentProvider(PaymentProvider):
    def __init__(self, outcomes: list[str] | None = None, webhook_secret: str | None = None):
        self.outcomes = list(outcomes or ["succeeded"])
        self.webhook_secret = webhook_secret.encode() if webhook_secret else secrets.token_bytes(32)
        self.intents: dict[str, ProviderPaymentIntent] = {}
        self.idempotency: dict[str, str] = {}

    def create_customer(self, organization_reference: str) -> ProviderCustomer:
        return ProviderCustomer(f"mock_cus_{hashlib.sha256(organization_reference.encode()).hexdigest()[:20]}")

    def attach_payment_method(self, customer_id: str, payment_method_token: str) -> ProviderPaymentMethod:
        if not payment_method_token.startswith("mock_pm_"):
            raise PaymentDeclined("invalid_payment_method", "Payment method token is invalid")
        return ProviderPaymentMethod(f"mock_method_{uuid.uuid4().hex}", "visa", "4242", 12, 2030)

    def create_payment_intent(self, customer_id: str | None, amount: Decimal, currency: str, idempotency_key: str) -> ProviderPaymentIntent:
        if idempotency_key in self.idempotency:
            return self.intents[self.idempotency[idempotency_key]]
        identifier = f"mock_pi_{uuid.uuid4().hex}"
        result = ProviderPaymentIntent(identifier, "requires_confirmation", amount, currency)
        self.intents[identifier] = result
        self.idempotency[idempotency_key] = identifier
        return result

    def confirm_payment(self, payment_intent_id: str) -> ProviderPaymentIntent:
        inject("PAYMENT_PROVIDER_UNAVAILABLE")
        current = self.intents.get(payment_intent_id)
        if current is None:
            raise PaymentProviderUnavailable("Mock payment intent not found")
        outcome = self.outcomes.pop(0) if self.outcomes else "succeeded"
        if outcome not in {"succeeded", "failed", "processing"}:
            raise PaymentProviderUnavailable("Mock provider unavailable")
        result = ProviderPaymentIntent(
            current.id, outcome, current.amount, current.currency,
            "card_declined" if outcome == "failed" else None,
            "Payment was declined" if outcome == "failed" else None,
        )
        self.intents[current.id] = result
        return result

    def create_subscription(self, customer_id: str, price_reference: str) -> ProviderSubscription:
        return ProviderSubscription(f"mock_sub_{uuid.uuid4().hex}", "active")

    def cancel_subscription(self, subscription_id: str) -> ProviderSubscription:
        return ProviderSubscription(subscription_id, "cancelled")

    def retry_invoice(self, invoice_id: str) -> str:
        return "succeeded"

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        expected = hmac.new(self.webhook_secret, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def get_payment_status(self, payment_intent_id: str) -> str:
        current = self.intents.get(payment_intent_id)
        if current is None:
            raise PaymentProviderUnavailable("Mock payment intent not found")
        return current.status

    def sign_webhook(self, payload: bytes) -> str:
        return hmac.new(self.webhook_secret, payload, hashlib.sha256).hexdigest()


class StripePaymentProviderStub(PaymentProvider):
    def _disabled(self, *args, **kwargs):
        raise PaymentProviderUnavailable("Stripe communication is disabled")

    create_customer = attach_payment_method = create_payment_intent = confirm_payment = _disabled
    create_subscription = cancel_subscription = retry_invoice = get_payment_status = _disabled

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        raise PaymentProviderUnavailable("Stripe webhook verification is disabled")
