from datetime import datetime, timezone
from sqlalchemy import update
from sqlalchemy.orm import Session
from app.models.billing import Estimate
from app.models.communications import Notification


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
