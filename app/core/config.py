import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    name: str
    environment: str
    database_url: str | None
    local_auth_enabled: bool = True
    local_auth_secret: str = "local-development-secret-change-me"
    frontend_origin: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        name=os.getenv("APP_NAME", "SystemNavigator AI"),
        environment=os.getenv("APP_ENV", "development"),
        database_url=os.getenv("APP_DATABASE_URL"),
        local_auth_enabled=os.getenv("APP_LOCAL_AUTH_ENABLED", "true").lower() == "true",
        local_auth_secret=os.getenv("APP_LOCAL_AUTH_SECRET", "local-development-secret-change-me"),
        frontend_origin=os.getenv("APP_FRONTEND_ORIGIN", "http://localhost:3000"),
    )
