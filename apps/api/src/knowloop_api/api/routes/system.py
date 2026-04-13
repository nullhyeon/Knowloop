from typing import Any

from fastapi import APIRouter, Request

from knowloop_api.api.context import get_server_request_id
from knowloop_api.api.errors import success_response
from knowloop_api.core.config import Settings
from knowloop_api.db.bootstrap import build_storage_readiness_payload
from knowloop_api.services.llm_runtime import build_llm_runtime_status


def create_system_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/system", tags=["system"])

    @router.get("/health")
    def system_health(request: Request) -> dict[str, Any]:
        return success_response(
            get_server_request_id(request),
            {
                "status": "ok",
            },
        )

    @router.get("/ready")
    def system_ready(request: Request) -> dict[str, Any]:
        return success_response(
            get_server_request_id(request),
            build_storage_readiness_payload(settings),
        )

    @router.get("/runtime")
    def system_runtime(request: Request) -> dict[str, Any]:
        return success_response(
            get_server_request_id(request),
            {
                "llm_runtime": build_llm_runtime_status(settings),
            },
        )

    return router
