from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.automation import router as automation_router
from app.api.billing import router as billing_router
from app.api.projects import router as projects_router
from app.api.system import router as system_router
from app.core.config import get_settings
from app.errors import AppError, ERROR_STATUS
from sqlalchemy.orm.exc import StaleDataError
from app.web.routes import router as web_router

BASE_DIR = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.name)
    application.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    application.include_router(web_router)
    application.include_router(system_router)
    application.include_router(projects_router)
    application.include_router(automation_router)
    application.include_router(billing_router)
    @application.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError):
        return JSONResponse(status_code=ERROR_STATUS[exc.code], content={"error": {"code": exc.code, "message": exc.message}})
    @application.exception_handler(StaleDataError)
    async def stale_data_handler(_request: Request, _exc: StaleDataError):
        return JSONResponse(status_code=409, content={"error": {"code": "VERSION_CONFLICT", "message": "Resource was updated by another request"}})
    return application


app = create_app()
