import pytest

from app.core.config import Settings
from app.db.session import DatabaseNotConfiguredError, create_database_engine


def test_database_is_optional_during_application_startup():
    settings = Settings(
        name="SystemNavigator AI",
        environment="test",
        database_url=None,
    )

    with pytest.raises(DatabaseNotConfiguredError, match="APP_DATABASE_URL"):
        create_database_engine(settings)


def test_database_rejects_non_postgresql_urls():
    settings = Settings(
        name="SystemNavigator AI",
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
    )

    with pytest.raises(DatabaseNotConfiguredError, match="PostgreSQL"):
        create_database_engine(settings)


def test_database_engine_creation_does_not_connect():
    settings = Settings(
        name="SystemNavigator AI",
        environment="test",
        database_url="postgresql+psycopg://user:secret@db.invalid/system_navigator",
    )

    engine = create_database_engine(settings)

    assert engine.url.host == "db.invalid"
    assert engine.url.render_as_string(hide_password=True).count("secret") == 0
    engine.dispose()
