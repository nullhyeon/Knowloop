from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from knowloop_api.api.context import RequestContext, get_learning_self_request_context
from knowloop_api.api.errors import success_response
from knowloop_api.core.config import Settings
from knowloop_api.services.learning import build_learning_console_payload


def create_learning_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/learning", tags=["learning"])

    @router.get("/self")
    def get_learning_self_endpoint(
        context: Annotated[RequestContext, Depends(get_learning_self_request_context)],
    ) -> dict[str, Any]:
        payload = build_learning_console_payload(
            settings,
            student_id=context.actor_id,
            course_id=context.course_id,
            class_id=context.class_id,
        )
        return success_response(
            context.request_id,
            payload.model_dump(mode="json"),
        )

    return router
