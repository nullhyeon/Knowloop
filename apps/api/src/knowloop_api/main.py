import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from knowloop_api.api.context import (
    RequestTracingContext,
    ensure_request_tracing_context,
    extract_client_request_id,
    get_request_tracing_context,
    get_server_request_id,
)
from knowloop_api.api.errors import ApiError
from knowloop_api.api.router import create_api_router
from knowloop_api.core.config import Settings, get_settings
from knowloop_api.core.input_limits import (
    MAX_QUERY_REQUEST_BODY_BYTES,
    MAX_REVIEW_REQUEST_BODY_BYTES,
    MAX_SOURCE_REGISTER_REQUEST_BODY_BYTES,
)
from knowloop_api.db.bootstrap import bootstrap_storage, build_storage_readiness_payload

logger = logging.getLogger(__name__)


class RequestBodyTooLargeError(Exception):
    def __init__(self, limit_bytes: int) -> None:
        self.limit_bytes = limit_bytes
        super().__init__(f"request body exceeds {limit_bytes} bytes")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    bootstrap_storage(resolved_settings)

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        description="Backend foundation for Knowloop.",
    )
    app.state.settings = resolved_settings

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        if not _is_api_route(request.url.path, resolved_settings.api_v1_prefix):
            return await call_next(request)

        tracing = ensure_request_tracing_context(
            request,
            extract_client_request_id(request),
        )
        body_limit = _resolve_request_body_limit(
            path=request.url.path,
            method=request.method,
            api_prefix=resolved_settings.api_v1_prefix,
            settings=resolved_settings,
        )
        if body_limit is not None:
            if _content_length_exceeds_limit(request, body_limit):
                return _body_too_large_response(
                    request,
                    tracing,
                    limit_bytes=body_limit,
                )
            _install_request_body_limit(request, body_limit)

        try:
            response = await call_next(request)
        except RequestBodyTooLargeError as exc:
            return _body_too_large_response(
                request,
                tracing,
                limit_bytes=exc.limit_bytes,
            )
        if "X-Request-Id" in response.headers:
            del response.headers["X-Request-Id"]
        if "X-Client-Request-Id" in response.headers:
            del response.headers["X-Client-Request-Id"]
        response.headers["X-Request-Id"] = tracing.request_id
        if tracing.client_request_id is not None:
            response.headers["X-Client-Request-Id"] = tracing.client_request_id
        return response

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if not _is_api_route(request.url.path, resolved_settings.api_v1_prefix):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=dict(exc.headers or {}),
            )

        request_id = get_server_request_id(request)
        tracing = get_request_tracing_context(request)
        code, message = _normalize_http_exception_error(exc)
        error = ApiError(
            status_code=exc.status_code,
            code=code,
            message=message,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=error.status_code,
            content=error.to_payload(request_id=request_id),
            headers=_build_error_headers(
                request_id=request_id,
                client_request_id=tracing.client_request_id,
                extra_headers=exc.headers,
            ),
        )

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        if not _is_api_route(request.url.path, resolved_settings.api_v1_prefix):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.message},
            )

        request_id = get_server_request_id(request)
        tracing = get_request_tracing_context(request)
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_payload(request_id=request_id),
            headers=_build_error_headers(
                request_id=request_id,
                client_request_id=tracing.client_request_id,
                retry_after_seconds=exc.retry_after_seconds,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        if not _is_api_route(request.url.path, resolved_settings.api_v1_prefix):
            return JSONResponse(
                status_code=422,
                content={"detail": exc.errors()},
            )

        request_id = get_server_request_id(request)
        tracing = get_request_tracing_context(request)
        error = ApiError(
            status_code=422,
            code="validation_failed",
            message="Request validation failed.",
            request_id=request_id,
            details={"errors": _sanitize_validation_errors(exc.errors())},
        )
        return JSONResponse(
            status_code=error.status_code,
            content=error.to_payload(request_id=request_id),
            headers=_build_error_headers(
                request_id=request_id,
                client_request_id=tracing.client_request_id,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        if not _is_api_route(request.url.path, resolved_settings.api_v1_prefix):
            logger.exception(
                "Unhandled non-api request error method=%s path=%s exception_type=%s",
                request.method,
                request.url.path,
                type(exc).__name__,
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal Server Error"},
            )

        request_id = get_server_request_id(request)
        tracing = get_request_tracing_context(request)
        logger.exception(
            "Unhandled request error request_id=%s method=%s path=%s exception_type=%s",
            request_id,
            request.method,
            request.url.path,
            type(exc).__name__,
        )
        error = ApiError(
            status_code=500,
            code="internal_error",
            message="An unexpected internal error occurred.",
            request_id=request_id,
        )
        return JSONResponse(
            status_code=error.status_code,
            content=error.to_payload(request_id=request_id),
            headers=_build_error_headers(
                request_id=request_id,
                client_request_id=tracing.client_request_id,
            ),
        )

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


def _resolve_request_body_limit(
    *,
    path: str,
    method: str,
    api_prefix: str,
    settings: Settings,
) -> int | None:
    if method.upper() not in {"POST", "PUT", "PATCH"}:
        return None
    normalized_prefix = api_prefix.rstrip("/")
    route_path = path.removeprefix(normalized_prefix).lstrip("/")
    route_limit = settings.max_api_request_body_bytes
    if route_path == "query/respond":
        route_limit = MAX_QUERY_REQUEST_BODY_BYTES
    elif route_path == "sources/register":
        route_limit = MAX_SOURCE_REGISTER_REQUEST_BODY_BYTES
    elif route_path.startswith("review/candidates/"):
        route_limit = MAX_REVIEW_REQUEST_BODY_BYTES
    return min(route_limit, settings.max_api_request_body_bytes)


def _content_length_exceeds_limit(request: Request, limit_bytes: int) -> bool:
    content_length = request.headers.get("content-length")
    if content_length is None:
        return False
    try:
        return int(content_length) > limit_bytes
    except ValueError:
        return False


def _install_request_body_limit(request: Request, limit_bytes: int) -> None:
    original_receive = request._receive
    received_bytes = 0

    async def limited_receive():
        nonlocal received_bytes
        message = await original_receive()
        if message.get("type") == "http.request":
            body = message.get("body", b"")
            received_bytes += len(body)
            if received_bytes > limit_bytes:
                raise RequestBodyTooLargeError(limit_bytes)
        return message

    request._receive = limited_receive


def _body_too_large_response(
    request: Request,
    tracing: RequestTracingContext,
    *,
    limit_bytes: int,
) -> JSONResponse:
    error = ApiError(
        status_code=413,
        code="body_too_large",
        message="Request body exceeds the configured limit.",
        request_id=tracing.request_id,
        details={
            "route": request.url.path,
            "limit_bytes": limit_bytes,
        },
    )
    return JSONResponse(
        status_code=error.status_code,
        content=error.to_payload(request_id=tracing.request_id),
        headers=_build_error_headers(
            request_id=tracing.request_id,
            client_request_id=tracing.client_request_id,
        ),
    )


def _build_error_headers(
    *,
    request_id: str,
    client_request_id: str | None = None,
    retry_after_seconds: int | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    headers = {
        key: value
        for key, value in dict(extra_headers or {}).items()
        if key.lower() not in {"x-request-id", "x-client-request-id"}
    }
    headers["X-Request-Id"] = request_id
    if client_request_id is not None:
        headers["X-Client-Request-Id"] = client_request_id
    if retry_after_seconds is not None:
        headers["Retry-After"] = str(retry_after_seconds)
    return headers


def _is_api_route(path: str, api_prefix: str) -> bool:
    normalized_prefix = api_prefix.rstrip("/")
    return path == normalized_prefix or path.startswith(f"{normalized_prefix}/")


def _normalize_http_exception_error(exc: StarletteHTTPException) -> tuple[str, str]:
    if exc.status_code == 404:
        return ("not_found", "Route was not found.")
    if exc.status_code == 403:
        return ("forbidden_scope", "Request could not access this API scope.")
    if exc.status_code == 422:
        return ("validation_failed", "Request validation failed.")
    if exc.status_code == 405:
        return ("invalid_request", "Method is not allowed for this route.")
    return (f"http_{exc.status_code}", "Request could not be completed.")


app = create_app()
