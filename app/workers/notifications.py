from app.services.communication_providers import (
    MockEmailProvider,
    MockNotificationProvider,
)
from datetime import datetime, timezone

from app.models.communications import (
    EmailMessage,
    Notification,
    NotificationDelivery,
    OutboxEvent,
)
from app.services.communications import deliver_notification, send_email_message
from app.workers.exceptions import NonRetryableWorkerError, TenantMismatch
from app.workers.registry import WorkerContext


def providers():
    return MockNotificationProvider(), MockEmailProvider()


class NotificationHandler:
    def execute(self, job: OutboxEvent, context: WorkerContext) -> None:
        delivery = context.session.get(NotificationDelivery, job.aggregate_id)
        if delivery is None:
            raise NonRetryableWorkerError("Notification delivery not found")
        notification = context.session.get(Notification, delivery.notification_id)
        if notification is None or notification.organization_id != job.organization_id:
            raise TenantMismatch("Notification organization mismatch")
        if (
            delivery.status == "failed"
            and delivery.attempt_count < delivery.max_attempts
        ):
            delivery.status = "scheduled"
        deliver_notification(
            context.session,
            delivery,
            context.notification_provider,
            datetime.now(timezone.utc),
        )
        if (
            delivery.status == "failed"
            and delivery.attempt_count >= delivery.max_attempts
        ):
            raise NonRetryableWorkerError("Notification attempts exhausted")


class EmailHandler:
    def execute(self, job: OutboxEvent, context: WorkerContext) -> None:
        message = context.session.get(EmailMessage, job.aggregate_id)
        if message is None:
            raise NonRetryableWorkerError("Email message not found")
        if message.organization_id != job.organization_id:
            raise TenantMismatch("Email organization mismatch")
        if message.status == "failed":
            message.status = "queued"
        send_email_message(
            context.session, message, context.email_provider, datetime.now(timezone.utc)
        )
        if message.status == "failed":
            raise RuntimeError("EMAIL_DELIVERY_FAILED")
