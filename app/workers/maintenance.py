from datetime import datetime, timezone
from sqlalchemy import update
from sqlalchemy.orm import Session
from app.models.billing import Estimate
from app.models.billing import MaintenanceContract
from app.models.communications import Notification
from app.models.communications import OutboxEvent
from app.services.billing import advance_maintenance_delinquency
from app.workers.exceptions import NonRetryableWorkerError, TenantMismatch
from app.workers.registry import WorkerContext


def run_daily(session: Session, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    expired = session.execute(
        update(Estimate)
        .where(
            Estimate.status.in_(["draft", "submitted"]),
            Estimate.valid_until < now.date(),
        )
        .values(status="expired")
    ).rowcount
    notifications = session.execute(
        update(Notification)
        .where(
            Notification.expires_at <= now,
            Notification.status.notin_(["read", "dismissed", "expired"]),
        )
        .values(status="expired")
    ).rowcount
    return {"expired_estimates": expired, "expired_notifications": notifications}


class MaintenanceHandler:
    def execute(self, job: OutboxEvent, context: WorkerContext) -> None:
        now = datetime.now(timezone.utc)
        if job.event_type in {"estimate_expiration", "notification_expiration"}:
            run_daily(context.session, now)
            return
        contract = context.session.get(MaintenanceContract, job.aggregate_id)
        if contract is None:
            raise NonRetryableWorkerError("Maintenance contract not found")
        if contract.organization_id != job.organization_id:
            raise TenantMismatch("Maintenance organization mismatch")
        advance_maintenance_delinquency(context.session, contract, now)
