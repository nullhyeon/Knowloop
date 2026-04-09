from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from knowloop_api.api.context import RequestContext, get_instructor_insight_request_context
from knowloop_api.api.errors import success_response
from knowloop_api.core.config import Settings
from knowloop_api.services.candidates import CandidateKind
from knowloop_api.services.insights import build_instructor_overview, list_candidate_patterns


def create_instructor_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/instructor/insights", tags=["instructor-insights"])

    @router.get("/overview")
    def get_instructor_overview_endpoint(
        context: Annotated[RequestContext, Depends(get_instructor_insight_request_context)],
    ) -> dict[str, Any]:
        overview = build_instructor_overview(
            settings,
            course_id=context.course_id,
            class_id=context.class_id,
        )
        return success_response(
            context.request_id,
            overview.model_dump(mode="json"),
        )

    @router.get("/patterns")
    def list_instructor_patterns_endpoint(
        context: Annotated[RequestContext, Depends(get_instructor_insight_request_context)],
        kind: Annotated[CandidateKind | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        patterns, total = list_candidate_patterns(
            settings,
            course_id=context.course_id,
            class_id=context.class_id,
            kind=kind,
            limit=limit,
            offset=offset,
        )
        return success_response(
            context.request_id,
            [pattern.model_dump(mode="json") for pattern in patterns],
            meta={
                "kind": kind.value if kind is not None else None,
                "limit": limit,
                "offset": offset,
                "total": total,
            },
        )

    return router
