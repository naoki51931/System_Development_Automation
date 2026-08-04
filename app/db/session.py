from collections.abc import Iterator
from contextlib import contextmanager
import time

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.performance_timing import current_timings


class DatabaseNotConfiguredError(RuntimeError):
    pass


def create_database_engine(settings: Settings | None = None) -> Engine:
    current_settings = settings or get_settings()
    if not current_settings.database_url:
        raise DatabaseNotConfiguredError("APP_DATABASE_URL is not configured")

    url = make_url(current_settings.database_url)
    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise DatabaseNotConfiguredError(
            "APP_DATABASE_URL must use PostgreSQL with psycopg"
        )

    engine = create_engine(url, pool_pre_ping=True)

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(_conn, _cursor, _statement, _parameters, context, _many):
        context._quality_started_at = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(_conn, _cursor, _statement, _parameters, context, _many):
        timings = current_timings()
        if timings is not None:
            timings["query"] = (
                timings.get("query", 0.0)
                + (time.perf_counter() - context._quality_started_at) * 1000
            )
            timings["sql_count"] = timings.get("sql_count", 0.0) + 1

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
    finally:
        session.close()
