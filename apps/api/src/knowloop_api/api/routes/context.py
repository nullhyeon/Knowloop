from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from knowloop_api.api.context import RequestContext, get_request_context
from knowloop_api.api.errors import success_response
from knowloop_api.core.config import Settings


def create_context_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/context", tags=["context"])

    @router.get("/self")
    def get_context_self_endpoint(
        context: Annotated[RequestContext, Depends(get_request_context)],
    ) -> dict[str, Any]:
        return success_response(
            context.request_id,
            {
                "profile_id": context.profile_id,
                "profile_label": context.profile_label,
                "role": context.role.value,
                "actor_id": context.actor_id,
                "course_id": context.course_id,
                "class_id": context.class_id,
                "domain": context.domain.value if context.domain is not None else None,
                "domain_was_explicit": context.domain_was_explicit,
            },
            meta={"context_source": _context_source_label(settings)},
        )

    return router


def _context_source_label(settings: Settings) -> str:
    if settings.context_trust_mode == "signed":
        return "signed_headers"
    return "headers"
