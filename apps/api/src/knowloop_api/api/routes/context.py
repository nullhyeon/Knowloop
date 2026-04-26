from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from knowloop_api.api.context import RequestContext, get_request_context, get_server_request_id
from knowloop_api.api.errors import ApiError, success_response
from knowloop_api.core.config import Settings
from knowloop_api.services.context_profiles import list_context_profiles


def create_context_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/context", tags=["context"])

    @router.get("/profiles")
    def list_context_profiles_endpoint(request: Request) -> dict[str, Any]:
        request_id = get_server_request_id(request)
        if not settings.demo_context_profiles_enabled:
            raise ApiError(
                status_code=403,
                code="demo_profiles_disabled",
                message="Context profiles are disabled outside explicit demo mode.",
                request_id=request_id,
            )
        profiles = list_context_profiles(settings)
        return success_response(
            request_id,
            [
                {
                    "profile_id": profile.profile_id,
                    "label": profile.label,
                    "role": profile.role.value,
                    "actor_id": profile.actor_id,
                    "course_id": profile.course_id,
                    "class_id": profile.class_id,
                    "domain": profile.domain.value,
                    "landing_surface": profile.landing_surface,
                    "description": profile.description,
                }
                for profile in profiles
            ],
            meta={"total": len(profiles)},
        )

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
            meta={"context_source": _context_source_label(settings, context)},
        )

    return router


def _context_source_label(settings: Settings, context: RequestContext) -> str:
    if context.profile_id is not None:
        return "profile"
    if settings.context_trust_mode == "signed":
        return "signed_headers"
    return "headers"
