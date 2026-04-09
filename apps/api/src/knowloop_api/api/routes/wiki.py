from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from knowloop_api.api.context import RequestContext, get_request_context
from knowloop_api.api.errors import ApiError, success_response
from knowloop_api.core.config import Settings
from knowloop_api.services.wiki import (
    ForbiddenWikiScopeError,
    WikiPageNotFoundError,
    get_visible_wiki_page,
    list_visible_wiki_pages,
)


def create_wiki_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/wiki", tags=["wiki"])

    @router.get("/pages")
    def list_wiki_pages_endpoint(
        context: Annotated[RequestContext, Depends(get_request_context)],
        q: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        normalized_query = (q or "").strip() or None
        try:
            pages, total = list_visible_wiki_pages(
                settings,
                role=context.role,
                course_id=context.course_id,
                class_id=context.class_id,
                requested_domain=context.domain,
                query=normalized_query,
                limit=limit,
                offset=offset,
            )
        except ForbiddenWikiScopeError as exc:
            raise ApiError(
                status_code=403,
                code="forbidden_scope",
                message=str(exc),
                request_id=context.request_id,
            ) from exc

        payload = [
            {
                "page_id": page.page_id,
                "domain": page.domain,
                "title": page.title,
                "summary": page.summary,
                "updated_at": page.updated_at.isoformat().replace("+00:00", "Z"),
            }
            for page in pages
        ]
        return success_response(
            context.request_id,
            payload,
            meta={
                "limit": limit,
                "offset": offset,
                "total": total,
                "query": normalized_query,
            },
        )

    @router.get("/pages/{page_id}")
    def get_wiki_page_endpoint(
        page_id: str,
        context: Annotated[RequestContext, Depends(get_request_context)],
    ) -> dict[str, Any]:
        try:
            page = get_visible_wiki_page(
                settings,
                page_id=page_id,
                role=context.role,
                course_id=context.course_id,
                class_id=context.class_id,
                requested_domain=context.domain,
            )
        except WikiPageNotFoundError as exc:
            raise ApiError(
                status_code=404,
                code="not_found",
                message="Wiki page was not found.",
                request_id=context.request_id,
                details={"page_id": page_id},
            ) from exc
        except ForbiddenWikiScopeError as exc:
            raise ApiError(
                status_code=403,
                code="forbidden_scope",
                message=str(exc),
                request_id=context.request_id,
                details={"page_id": page_id},
            ) from exc

        payload = {
            "page_id": page.page_id,
            "domain": page.domain,
            "title": page.title,
            "summary": page.summary,
            "course_id": page.course_id,
            "class_scope": page.class_scope,
            "updated_at": page.updated_at.isoformat().replace("+00:00", "Z"),
            "source_refs": page.source_refs,
            "candidate_refs": page.candidate_refs,
            "body_markdown": page.body_markdown,
        }
        return success_response(context.request_id, payload)

    return router
