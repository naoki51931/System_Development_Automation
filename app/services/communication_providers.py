import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from app.testing.faults import inject


class NotificationProviderError(Exception):
    pass


class NotificationProviderUnavailable(NotificationProviderError):
    pass


class EmailProviderError(Exception):
    pass


class EmailProviderUnavailable(EmailProviderError):
    pass


@dataclass(frozen=True)
class DeliveryResult:
    provider_message_id: str
    status: str


class NotificationProvider(ABC):
    @abstractmethod
    def send(
        self, *, recipient_reference: str, title: str, body: str
    ) -> DeliveryResult: ...
    @abstractmethod
    def get_status(self, provider_message_id: str) -> str: ...
    @abstractmethod
    def test_connection(self) -> bool: ...


class MockNotificationProvider(NotificationProvider):
    def __init__(self, outcomes: list[str] | None = None):
        self.outcomes = list(outcomes or ["delivered"])
        self.messages: dict[str, str] = {}

    def send(
        self, *, recipient_reference: str, title: str, body: str
    ) -> DeliveryResult:
        outcome = self.outcomes.pop(0) if self.outcomes else "delivered"
        if outcome == "unavailable":
            raise NotificationProviderUnavailable("Mock notification unavailable")
        identifier = f"mock_notification_{uuid.uuid4().hex}"
        self.messages[identifier] = outcome
        return DeliveryResult(identifier, outcome)

    def get_status(self, provider_message_id: str) -> str:
        return self.messages.get(provider_message_id, "unknown")

    def test_connection(self) -> bool:
        return True


class InAppNotificationProvider(MockNotificationProvider):
    pass


class EmailProvider(ABC):
    @abstractmethod
    def send_email(
        self,
        *,
        recipient: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> DeliveryResult: ...
    @abstractmethod
    def get_delivery_status(self, provider_message_id: str) -> str: ...
    @abstractmethod
    def test_connection(self) -> bool: ...


class MockEmailProvider(EmailProvider):
    def __init__(self, outcomes: list[str] | None = None):
        self.outcomes = list(outcomes or ["delivered"])
        self.messages: dict[str, dict[str, str | None]] = {}

    def send_email(
        self,
        *,
        recipient: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> DeliveryResult:
        inject("EMAIL_PROVIDER_FAILURE")
        outcome = self.outcomes.pop(0) if self.outcomes else "delivered"
        if outcome == "unavailable":
            raise EmailProviderUnavailable("Mock email unavailable")
        identifier = f"mock_email_{uuid.uuid4().hex}"
        self.messages[identifier] = {
            "recipient": recipient,
            "subject": subject,
            "body_text": body_text,
            "body_html": body_html,
            "status": outcome,
        }
        return DeliveryResult(identifier, outcome)

    def get_delivery_status(self, provider_message_id: str) -> str:
        value = self.messages.get(provider_message_id)
        return str(value["status"]) if value else "unknown"

    def test_connection(self) -> bool:
        return True


class DisabledEmailProvider(EmailProvider):
    def _disabled(self, *args, **kwargs):
        raise EmailProviderUnavailable("External email communication is disabled")

    send_email = _disabled
    get_delivery_status = _disabled

    def test_connection(self) -> bool:
        return False


class SESEmailProviderStub(DisabledEmailProvider):
    pass


class SMTPEmailProviderStub(DisabledEmailProvider):
    pass
