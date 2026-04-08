from typing import Any

from fastapi import FastAPI

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


app = create_app()
