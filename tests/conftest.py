import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@pytest.fixture(scope="session")
def database_url() -> str:
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    return value


@pytest.fixture(scope="session")
def migrated_engine(database_url: str):  # type: ignore[no-untyped-def]
    old_value = os.environ.get("APP_DATABASE_URL")
    os.environ["APP_DATABASE_URL"] = database_url
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(database_url)
    yield engine
    engine.dispose()
    if old_value is None:
        os.environ.pop("APP_DATABASE_URL", None)
    else:
        os.environ["APP_DATABASE_URL"] = old_value
    get_settings.cache_clear()


@pytest.fixture()
def db_session(migrated_engine):  # type: ignore[no-untyped-def]
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    session: Session = factory()
    yield session
    session.rollback()
    session.close()
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE review_comments, reviews, approval_events, artifact_versions, artifacts, ai_runs, project_members, projects, audit_logs, membership_roles, organization_memberships, "
                "workflow_jobs, artifact_upload_intents, ai_settings, roles, users, organizations CASCADE"
            )
        )
