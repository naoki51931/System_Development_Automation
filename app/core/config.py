import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    name: str
    environment: str
    database_url: str | None


@lru_cache
def get_settings() -> Settings:
    return Settings(
        name=os.getenv("APP_NAME", "SystemNavigator AI"),
        environment=os.getenv("APP_ENV", "development"),
        database_url=os.getenv("APP_DATABASE_URL"),
    )
