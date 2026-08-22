import argparse
import os
import socket
import threading
import time

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import create_database_engine, create_session_factory
from app.models.communications import OutboxEvent
from app.testing.faults import InjectedFault, inject
from app.workers.exceptions import LeaseLost, NonRetryableWorkerError, WorkerError
from app.workers.health import WorkerStatus
from app.workers.metrics import production_metrics_from_environment
from app.workers.outbox import claim, complete_owned, fail, heartbeat_owned
from app.workers.registry import WorkerContext, default_registry, resolve_job_type


class LeaseHeartbeat:
    def __init__(self, factory, job_id, worker_id, *, lease_seconds=60, interval=20):
        self.factory = factory
        self.job_id = job_id
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.interval = interval
        self.stop_event = threading.Event()
        self.lost = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self.stop_event.wait(self.interval):
            try:
                with self.factory.begin() as session:
                    if not heartbeat_owned(
                        session, self.job_id, self.worker_id, self.lease_seconds
                    ):
                        self.lost.set()
                        return
            except Exception:
                # A DB outage makes ownership unverifiable; stop further work.
                self.lost.set()
                return

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop_event.set()
        self.thread.join(timeout=max(1, self.interval + 1))


def _failure_code(exc: Exception) -> str:
    if isinstance(exc, WorkerError):
        return exc.code
    if isinstance(exc, InjectedFault):
        return exc.code[:100]
    return "HANDLER_FAILED"


def run_once(
    factory,
    worker_id: str,
    *,
    registry=None,
    lease_seconds=60,
    heartbeat_interval=20,
    status: WorkerStatus | None = None,
) -> bool:
    registry = registry or default_registry()
    with factory.begin() as session:
        job = claim(session, worker_id, lease_seconds)
        if not job:
            if status:
                status.poll()
            return False
        job_id = job.id
    error: Exception | None = None
    heartbeat = LeaseHeartbeat(
        factory,
        job_id,
        worker_id,
        lease_seconds=lease_seconds,
        interval=heartbeat_interval,
    )
    try:
        with heartbeat:
            inject("WORKER_CRASH_AFTER_CLAIM")
            with factory.begin() as session:
                current = session.scalar(
                    select(OutboxEvent).where(
                        OutboxEvent.id == job_id,
                        OutboxEvent.status == "processing",
                        OutboxEvent.locked_by == worker_id,
                    )
                )
                if current is None or heartbeat.lost.is_set():
                    raise LeaseLost("Worker lease was lost")
                handler = registry.get(resolve_job_type(current))
                handler.execute(current, WorkerContext(session, worker_id))
                session.flush()
                if heartbeat.lost.is_set():
                    raise LeaseLost("Worker lease was lost")
        with factory.begin() as session:
            if not complete_owned(session, job_id, worker_id):
                raise LeaseLost("Worker lease was lost before completion")
    except Exception as exc:
        error = exc
        with factory.begin() as session:
            current = session.get(OutboxEvent, job_id)
            if (
                current
                and current.status == "processing"
                and current.locked_by == worker_id
            ):
                # Unknown/non-retryable jobs go directly to dead letter.
                if isinstance(exc, NonRetryableWorkerError):
                    current.attempt_count = current.max_attempts
                fail(session, current, _failure_code(exc))
    finally:
        if status:
            status.poll(heartbeat=True, error=_failure_code(error) if error else None)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=2)
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument("--heartbeat-interval", type=float, default=20)
    args = parser.parse_args()
    factory = create_session_factory(create_database_engine(get_settings()))
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    status = WorkerStatus(
        factory, worker_id, metrics=production_metrics_from_environment()
    )
    status.poll()
    while True:
        worked = run_once(
            factory,
            worker_id,
            lease_seconds=args.lease_seconds,
            heartbeat_interval=args.heartbeat_interval,
            status=status,
        )
        if args.once:
            break
        if not worked:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
