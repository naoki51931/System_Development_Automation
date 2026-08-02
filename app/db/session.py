from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


class DatabaseNotConfiguredError(RuntimeError):
    pass


def create_database_engine(settings: Settings | None = None) -> Engine:
    current_settings = settings or get_settings()
    if not current_settings.database_url:
        raise DatabaseNotConfiguredError("APP_DATABASE_URL is not configured")

    url = make_url(current_settings.database_url)
    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise DatabaseNotConfiguredError("APP_DATABASE_URL must use PostgreSQL with psycopg")

    return create_engine(url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
    finally:
        session.close()
