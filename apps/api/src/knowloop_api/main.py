from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from knowloop_api.api.context import build_request_id
from knowloop_api.api.errors import ApiError
from knowloop_api.api.router import create_api_router
from knowloop_api.core.config import Settings, get_settings
from knowloop_api.db.bootstrap import bootstrap_storage, build_storage_readiness_payload


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    bootstrap_storage(resolved_settings)

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        description="Backend foundation for Knowloop.",
    )

    @app.exception_handler(ApiError)
    async def handle_api_error(_request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request, exc: RequestValidationError) -> JSONResponse:
        request_id = request.headers.get("X-Request-Id") or build_request_id()
        error = ApiError(
            status_code=422,
            code="validation_failed",
            message="Request validation failed.",
            request_id=request_id,
            details={"errors": _sanitize_validation_errors(exc.errors())},
        )
        return JSONResponse(status_code=error.status_code, content=error.to_payload())

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = request.headers.get("X-Request-Id") or build_request_id()
        error = ApiError(
            status_code=500,
            code="internal_error",
            message="An unexpected internal error occurred.",
            request_id=request_id,
        )
        return JSONResponse(status_code=error.status_code, content=error.to_payload())

    @app.get("/", tags=["system"])
    def root() -> dict[str, str]:
        return {
            "service": resolved_settings.app_name,
            "status": "ok",
            "environment": resolved_settings.app_env,
        }

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {
            "status": "ok",
            "environment": resolved_settings.app_env,
        }

    @app.get("/readyz", tags=["system"])
    def readyz() -> dict[str, Any]:
        return build_storage_readiness_payload(resolved_settings)

    app.include_router(create_api_router(resolved_settings), prefix=resolved_settings.api_v1_prefix)
    return app


def _sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "loc": list(error.get("loc", [])),
            "type": error.get("type"),
            "message": error.get("msg"),
        }
        for error in errors
    ]


app = create_app()
