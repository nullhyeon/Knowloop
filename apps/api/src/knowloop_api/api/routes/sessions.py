from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from knowloop_api.api.context import RequestContext, get_session_search_request_context
from knowloop_api.api.errors import ApiError, success_response
from knowloop_api.core.config import Settings
from knowloop_api.services.session_search import (
    ForbiddenSessionSearchError,
    list_recent_session_hits,
    search_sessions,
)


def create_sessions_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/sessions", tags=["sessions"])

    @router.get("/search")
    def search_sessions_endpoint(
        context: Annotated[RequestContext, Depends(get_session_search_request_context)],
        q: Annotated[str, Query(min_length=1)] = "",
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        normalized_query = q.strip()
        if not normalized_query:
            raise ApiError(
                status_code=422,
                code="validation_failed",
                message="q must not be blank.",
                request_id=context.request_id,
            )
        try:
            hits, total = search_sessions(
                settings,
                role=context.role,
                actor_id=context.actor_id,
                course_id=context.course_id,
                class_id=context.class_id,
                query=normalized_query,
                limit=limit,
                offset=offset,
            )
        except ForbiddenSessionSearchError as exc:
            raise ApiError(
                status_code=403,
                code="forbidden_scope",
                message=str(exc),
                request_id=context.request_id,
            ) from exc

        return success_response(
            context.request_id,
            [hit.model_dump(mode="json") for hit in hits],
            meta={
                "query": normalized_query,
                "limit": limit,
                "offset": offset,
                "total": total,
            },
        )

    @router.get("/recent")
    def list_recent_sessions_endpoint(
        context: Annotated[RequestContext, Depends(get_session_search_request_context)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        try:
            hits, total = list_recent_session_hits(
                settings,
                role=context.role,
                actor_id=context.actor_id,
                course_id=context.course_id,
                class_id=context.class_id,
                limit=limit,
                offset=offset,
            )
        except ForbiddenSessionSearchError as exc:
            raise ApiError(
                status_code=403,
                code="forbidden_scope",
                message=str(exc),
                request_id=context.request_id,
            ) from exc

        return success_response(
            context.request_id,
            [hit.model_dump(mode="json") for hit in hits],
            meta={
                "limit": limit,
                "offset": offset,
                "total": total,
            },
        )

    return router
