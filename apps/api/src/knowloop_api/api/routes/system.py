from typing import Any

from fastapi import APIRouter

from knowloop_api.core.config import Settings
from knowloop_api.db.bootstrap import build_storage_readiness_payload


def create_system_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/system", tags=["system"])

    @router.get("/health")
    def system_health() -> dict[str, Any]:
        return {
            "request_id": "system-health",
            "data": {
                "status": "ok",
            },
            "meta": {},
        }

    @router.get("/ready")
    def system_ready() -> dict[str, Any]:
        return {
            "request_id": "system-ready",
            "data": build_storage_readiness_payload(settings),
            "meta": {},
        }

    return router
