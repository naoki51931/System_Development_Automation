import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.models.communications import OutboxEvent


def utcnow():
    return datetime.now(timezone.utc)


def claim(
    session: Session, worker_id: str, lease_seconds: int = 60
) -> OutboxEvent | None:
    now = utcnow()
    job = session.scalar(
        select(OutboxEvent)
        .where(
            OutboxEvent.available_at <= now,
            or_(
                OutboxEvent.status.in_(["pending", "queued", "retry_wait"]),
                (OutboxEvent.status == "processing")
                & (OutboxEvent.lease_expires_at < now),
            ),
        )
        .order_by(OutboxEvent.available_at, OutboxEvent.created_at, OutboxEvent.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job:
        job.status, job.locked_at, job.locked_by = "processing", now, worker_id
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.heartbeat_at = now
        job.attempt_count += 1
        session.flush()
    return job


def heartbeat(
    session: Session, job: OutboxEvent, worker_id: str, lease_seconds: int = 60
) -> bool:
    if job.status != "processing" or job.locked_by != worker_id:
        return False
    now = utcnow()
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    session.flush()
    return True


def complete(session: Session, job: OutboxEvent) -> None:
    job.status = "completed"
    job.processed_at = utcnow()
    job.lease_expires_at = None
    job.last_error_code = None


def fail(session: Session, job: OutboxEvent, error_code: str) -> None:
    now = utcnow()
    job.last_error_code = error_code[:100]
    job.locked_by = None
    job.lease_expires_at = None
    if job.attempt_count >= job.max_attempts:
        job.status = "dead_letter"
        job.dead_lettered_at = now
    else:
        job.status = "retry_wait"
        job.available_at = now + timedelta(
            seconds=min(3600, (2**job.attempt_count) + secrets.randbelow(1000) / 1000)
        )


def retry_dead_letter(session: Session, job: OutboxEvent) -> None:
    if job.status != "dead_letter":
        raise ValueError("Job is not dead-lettered")
    job.status = "queued"
    job.attempt_count = 0
    job.dead_lettered_at = None
    job.available_at = utcnow()
    job.last_error_code = None
