from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from knowloop_api.api.context import (
    RequestContext,
    get_maintenance_report_request_context,
    get_maintenance_status_request_context,
)
from knowloop_api.api.errors import success_response
from knowloop_api.core.config import Settings
from knowloop_api.services.maintenance import build_maintenance_report, load_maintenance_report


def create_maintenance_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/maintenance", tags=["maintenance"])

    @router.get("/report")
    def get_maintenance_report_endpoint(
        context: Annotated[RequestContext, Depends(get_maintenance_report_request_context)],
    ) -> dict[str, Any]:
        report = build_maintenance_report(
            settings,
            course_id=context.course_id,
            class_id=context.class_id,
        )
        return success_response(
            context.request_id,
            report.model_dump(mode="json"),
        )

    @router.get("/status")
    def get_maintenance_status_endpoint(
        context: Annotated[RequestContext, Depends(get_maintenance_status_request_context)],
    ) -> dict[str, Any]:
        report = load_maintenance_report(
            settings,
            course_id=context.course_id,
            class_id=context.class_id,
        )
        return success_response(
            context.request_id,
            report.model_dump(mode="json"),
        )

    return router
