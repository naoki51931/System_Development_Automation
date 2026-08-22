import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db.session import create_database_engine, create_session_factory
from app.models.communications import OutboxEvent
from app.workers.metrics import publish_or_log

STATUS_PATH = Path(
    os.getenv(
        "APP_WORKER_HEALTH_FILE",
        str(Path(tempfile.gettempdir()) / "systemnavigator-worker-health.json"),
    )
)


class WorkerStatus:
    def __init__(self, factory, worker_id: str, path: Path = STATUS_PATH, metrics=None):
        self.factory, self.worker_id, self.path, self.metrics = (
            factory,
            worker_id,
            path,
            metrics,
        )
        self.started_at = datetime.now(timezone.utc)

    def poll(self, *, heartbeat=False, error=None):
        now = datetime.now(timezone.utc)
        with self.factory() as session:
            session.execute(text("SELECT 1"))
            dead_letters = (
                session.scalar(
                    select(func.count())
                    .select_from(OutboxEvent)
                    .where(OutboxEvent.status == "dead_letter")
                )
                or 0
            )
        prior = {}
        try:
            prior = json.loads(self.path.read_text())
        except (OSError, ValueError):
            pass
        data = {
            "worker_id": self.worker_id,
            "pid": os.getpid(),
            "started_at": self.started_at.isoformat(),
            "last_poll_at": now.isoformat(),
            "last_heartbeat_at": now.isoformat()
            if heartbeat
            else prior.get("last_heartbeat_at"),
            "dead_letter_count": dead_letters,
            "last_error_code": error,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".worker-health-")
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, sort_keys=True)
        os.replace(temporary, self.path)
        publish_or_log(
            self.metrics,
            heartbeat_age_seconds=0,
            dead_letter_count=dead_letters,
        )


def check(path: Path = STATUS_PATH, max_poll_age=30) -> tuple[bool, str]:
    try:
        data = json.loads(path.read_text())
        polled = datetime.fromisoformat(data["last_poll_at"])
        if datetime.now(timezone.utc) - polled > timedelta(seconds=max_poll_age):
            return False, "poll_stale"
        os.kill(int(data["pid"]), 0)
        factory = create_session_factory(create_database_engine(get_settings()))
        with factory() as session:
            session.execute(text("SELECT 1"))
        return True, "healthy"
    except Exception:
        return False, "unhealthy"


def main():
    healthy, reason = check()
    print(json.dumps({"status": reason}))
    raise SystemExit(0 if healthy else 1)


if __name__ == "__main__":
    main()
