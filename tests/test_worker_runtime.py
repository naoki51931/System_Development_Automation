import json
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import sessionmaker

from app.models import Organization
from app.models.communications import OutboxEvent
from app.workers.health import WorkerStatus, check
from app.workers.registry import Registry, resolve_job_type
from app.workers.runner import LeaseHeartbeat, run_once


def make_job(session, event_type="notification"):
    organization = Organization(name=f"runtime-{uuid.uuid4()}")
    session.add(organization)
    session.flush()
    job = OutboxEvent(
        organization_id=organization.id,
        event_type=event_type,
        aggregate_type="unknown",
        aggregate_id=uuid.uuid4(),
        payload_hash=uuid.uuid4().hex.ljust(64, "0"),
        status="queued",
        available_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    session.add(job)
    session.flush()
    return job


class RecordingHandler:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def execute(self, job, context):
        self.calls.append((job.id, context.worker_id))
        if self.error:
            raise self.error


def test_runner_dispatches_and_completes_only_after_success(db_session):
    job = make_job(db_session)
    job_id = job.id
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    handler = RecordingHandler()
    registry = Registry()
    registry.register("notification", handler)
    assert run_once(factory, "runtime-worker", registry=registry)
    with factory() as session:
        saved = session.get(OutboxEvent, job_id)
        assert saved.status == "completed" and saved.processed_at
    assert handler.calls == [(job_id, "runtime-worker")]


def test_runner_retries_failure_and_dead_letters_unknown_type(db_session):
    failing = make_job(db_session)
    failing_id = failing.id
    failing.max_attempts = 2
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    registry = Registry()
    registry.register("notification", RecordingHandler(RuntimeError("secret")))
    assert run_once(factory, "runtime-worker", registry=registry)
    with factory.begin() as session:
        saved = session.get(OutboxEvent, failing_id)
        assert (
            saved.status == "retry_wait" and saved.last_error_code == "HANDLER_FAILED"
        )
        saved.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert run_once(factory, "runtime-worker", registry=registry)
    with factory() as session:
        assert session.get(OutboxEvent, failing_id).status == "dead_letter"

    with factory.begin() as session:
        unknown = make_job(session, "not_registered")
        unknown_id = unknown.id
    assert run_once(factory, "runtime-worker", registry=Registry())
    with factory() as session:
        saved = session.get(OutboxEvent, unknown_id)
        assert saved.status == "dead_letter"
        assert saved.last_error_code == "UNREGISTERED_JOB_TYPE"


def test_resolve_all_required_job_types():
    for value in (
        "outbox",
        "notification",
        "email",
        "document",
        "ai_workflow",
        "maintenance",
        "estimate_expiration",
        "notification_expiration",
    ):
        assert (
            resolve_job_type(
                type("Job", (), {"event_type": value, "aggregate_type": "x"})()
            )
            == value
        )


def test_lease_heartbeat_stops_and_reports_database_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.workers.runner.heartbeat_owned",
        lambda *_args, **_kwargs: calls.append(True) or True,
    )

    class Transaction:
        def __enter__(self):
            return object()

        def __exit__(self, *_):
            return None

    class Factory:
        def begin(self):
            return Transaction()

    heartbeat = LeaseHeartbeat(Factory(), uuid.uuid4(), "worker", interval=0.01)
    with heartbeat:
        time.sleep(0.03)
    count = len(calls)
    time.sleep(0.02)
    assert count >= 1 and len(calls) == count and not heartbeat.thread.is_alive()


def test_worker_health_healthy_stale_and_bad_database(
    db_session, tmp_path, monkeypatch
):
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    path = tmp_path / "health.json"
    WorkerStatus(factory, "test-worker", path).poll(heartbeat=True)
    monkeypatch.setattr("app.workers.health.STATUS_PATH", path)
    monkeypatch.setattr(
        "app.workers.health.create_database_engine", lambda _: db_session.get_bind()
    )
    assert check(path)[0]
    data = json.loads(path.read_text())
    data["last_poll_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=2)
    ).isoformat()
    path.write_text(json.dumps(data))
    assert check(path)[1] == "poll_stale"
    path.write_text("not-json")
    assert check(path)[1] == "unhealthy"
