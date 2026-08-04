from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.api.automation import router as automation_router
from app.api.billing import router as billing_router
from app.api.communications import router as communications_router
from app.api.projects import router as projects_router
from app.api.system import router as system_router
from app.core.config import get_settings
from app.db.session import create_database_engine, create_session_factory
from app.auth.verifier import LocalAuthProvider, CognitoAuthProviderStub
from app.errors import AppError, ERROR_STATUS
from app.testing.faults import InjectedFault
from app.performance_timing import reset_request_timing, start_request_timing
from sqlalchemy.orm.exc import StaleDataError
from app.web.routes import router as web_router
from app.api.local_auth import router as local_auth_router
from app.api.admin import router as admin_router
from app.api.collections import router as collections_router

BASE_DIR = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.name)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Authorization"],
    )
    if settings.database_url:
        application.state.session_factory = create_session_factory(
            create_database_engine(settings)
        )
    if (
        settings.environment.lower() not in {"production", "prod"}
        and settings.local_auth_enabled
    ):
        application.state.token_verifier = LocalAuthProvider(settings.local_auth_secret)
    else:
        application.state.token_verifier = CognitoAuthProviderStub()
    application.mount(
        "/static", StaticFiles(directory=BASE_DIR / "static"), name="static"
    )
    application.include_router(web_router)
    application.include_router(system_router)
    application.include_router(projects_router)
    application.include_router(automation_router)
    application.include_router(billing_router)
    application.include_router(communications_router)
    application.include_router(local_auth_router)
    application.include_router(admin_router)
    application.include_router(collections_router)

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        timing_token = None
        timings = None
        started_at = perf_counter()
        if settings.performance_timing_enabled:
            timing_token, timings = start_request_timing()
        try:
            response = await call_next(request)
        finally:
            if timing_token is not None:
                reset_request_timing(timing_token)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
        )
        if timings is not None:
            timings["total"] = (perf_counter() - started_at) * 1000
            timings["response_size"] = float(response.headers.get("content-length", 0))
            response.headers["Server-Timing"] = (
                ", ".join(
                    f"{name};dur={value:.3f}"
                    for name, value in timings.items()
                    if name != "sql_count"
                )
                + f', sql_count;desc="{int(timings["sql_count"])}"'
            )
        return response

    @application.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError):
        return JSONResponse(
            status_code=ERROR_STATUS[exc.code],
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @application.exception_handler(StaleDataError)
    async def stale_data_handler(_request: Request, _exc: StaleDataError):
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "VERSION_CONFLICT",
                    "message": "Resource was updated by another request",
                }
            },
        )

    @application.exception_handler(InjectedFault)
    async def injected_fault_handler(_request: Request, exc: InjectedFault):
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": exc.code,
                    "message": "Local mock provider is temporarily unavailable",
                }
            },
        )

    return application


app = create_app()
