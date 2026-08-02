from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.projects import router as projects_router
from app.api.system import router as system_router
from app.core.config import get_settings
from app.web.routes import router as web_router

BASE_DIR = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.name)
    application.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    application.include_router(web_router)
    application.include_router(system_router)
    application.include_router(projects_router)
    return application


app = create_app()
