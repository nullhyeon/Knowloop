from fastapi import FastAPI

from knowloop_api.api.router import api_router
from knowloop_api.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Backend foundation for Knowloop.",
    )

    @app.get("/", tags=["system"])
    def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "status": "ok",
            "environment": settings.app_env,
        }

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {
            "status": "ok",
            "environment": settings.app_env,
        }

    @app.get("/readyz", tags=["system"])
    def readyz() -> dict[str, str]:
        return {
            "status": "ready",
            "database_path": str(settings.database_path),
        }

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
