from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from knowloop_api.api.context import (
    RequestContext,
    get_public_query_request_context,
)
from knowloop_api.api.errors import ApiError, success_response
from knowloop_api.core.config import Settings
from knowloop_api.services.query import (
    ForbiddenQueryScopeError,
    InsufficientVerifiedContextError,
    QueryReplayConflictError,
    QueryRequest,
    QueryStateError,
    QueryStorageBusyError,
    build_query_runtime_meta,
    respond_to_query,
)


def create_query_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/query", tags=["query"])

    @router.post("/respond")
    def respond_to_query_endpoint(
        payload: QueryRequest,
        context: Annotated[RequestContext, Depends(get_public_query_request_context)],
    ) -> dict[str, Any]:
        try:
            response = respond_to_query(settings, payload, context=context)
        except InsufficientVerifiedContextError as exc:
            raise ApiError(
                status_code=409,
                code="insufficient_verified_context",
                message=str(exc),
                request_id=context.request_id,
            ) from exc
        except ForbiddenQueryScopeError as exc:
            raise ApiError(
                status_code=403,
                code="forbidden_scope",
                message=str(exc),
                request_id=context.request_id,
            ) from exc
        except QueryReplayConflictError as exc:
            raise ApiError(
                status_code=409,
                code="duplicate_action",
                message=str(exc),
                request_id=context.request_id,
            ) from exc
        except QueryStorageBusyError as exc:
            raise ApiError(
                status_code=503,
                code="storage_busy",
                message=str(exc),
                request_id=context.request_id,
            ) from exc
        except QueryStateError as exc:
            raise ApiError(
                status_code=400,
                code="invalid_request",
                message=str(exc),
                request_id=context.request_id,
            ) from exc

        return success_response(
            context.request_id,
            response.model_dump(mode="json", exclude_none=True),
            meta={"runtime": build_query_runtime_meta(settings, response=response)},
        )

    return router
