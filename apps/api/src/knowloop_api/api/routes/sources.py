from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from knowloop_api.api.context import RequestContext, get_request_context
from knowloop_api.api.errors import ApiError, success_response
from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import (
    ActorRole,
    RequestDomain,
    SourceType,
    is_source_type_allowed_for_role,
)
from knowloop_api.services.sources import (
    SourceLockError,
    SourceNotFoundError,
    SourceRegistrationInput,
    SourceStateError,
    get_source,
    is_source_visible_to_role,
    list_sources,
    register_source,
    source_record_to_response_payload,
)


def create_sources_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/sources", tags=["sources"])

    @router.post("/register", status_code=status.HTTP_201_CREATED)
    def register_source_endpoint(
        payload: SourceRegistrationInput,
        context: Annotated[RequestContext, Depends(get_request_context)],
    ) -> dict[str, Any]:
        if context.idempotency_key is None or not context.idempotency_key.strip():
            raise ApiError(
                status_code=422,
                code="validation_failed",
                message="Idempotency-Key is required for source registration.",
                request_id=context.request_id,
                details={"header": "Idempotency-Key"},
            )
        if context.role not in {ActorRole.INSTRUCTOR, ActorRole.OPERATOR, ActorRole.SYSTEM}:
            raise ApiError(
                status_code=403,
                code="forbidden_role",
                message="This role cannot register raw sources.",
                request_id=context.request_id,
                details={"role": context.role.value},
            )

        if context.role is ActorRole.SYSTEM and context.domain is RequestDomain.REVIEW:
            raise ApiError(
                status_code=422,
                code="validation_failed",
                message="Raw source registration does not support the review domain.",
                request_id=context.request_id,
                details={"domain": context.domain.value},
            )
        if not is_source_type_allowed_for_role(
            payload.source_type,
            actor_role=context.role,
            requested_domain=context.domain,
        ):
            raise ApiError(
                status_code=403,
                code="forbidden_scope",
                message="This role cannot register that source type in the current domain.",
                request_id=context.request_id,
                details={"source_type": payload.source_type.value},
            )
        if (
            context.role is ActorRole.SYSTEM
            and payload.source_type is SourceType.ANNOUNCEMENT
            and context.domain is None
        ):
            raise ApiError(
                status_code=422,
                code="validation_failed",
                message="X-Knowloop-Domain is required for announcement registration.",
                request_id=context.request_id,
                details={"source_type": payload.source_type.value},
            )

        try:
            source_record = register_source(
                settings,
                payload,
                course_id=context.course_id,
                class_id=context.class_id,
                actor_role=context.role,
                actor_id=context.actor_id,
                domain=context.domain,
                request_id=context.request_id,
                idempotency_key=context.idempotency_key,
            )
        except FileExistsError as exc:
            raise ApiError(
                status_code=409,
                code="duplicate_action",
                message=str(exc),
                request_id=context.request_id,
                details={"source_type": payload.source_type.value},
            ) from exc
        except SourceLockError as exc:
            raise ApiError(
                status_code=503,
                code="storage_busy",
                message=str(exc),
                request_id=context.request_id,
                details={"source_type": payload.source_type.value},
            ) from exc
        except SourceStateError as exc:
            raise ApiError(
                status_code=409,
                code="duplicate_action",
                message=str(exc),
                request_id=context.request_id,
                details={"source_type": payload.source_type.value},
            ) from exc

        return success_response(
            context.request_id,
            source_record_to_response_payload(source_record),
        )

    @router.get("")
    def list_sources_endpoint(
        context: Annotated[RequestContext, Depends(get_request_context)],
        source_type: Annotated[SourceType | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
        q: Annotated[str | None, Query()] = None,
    ) -> dict[str, Any]:
        if context.role not in {
            ActorRole.INSTRUCTOR,
            ActorRole.OPERATOR,
            ActorRole.VALIDATOR,
            ActorRole.SYSTEM,
        }:
            raise ApiError(
                status_code=403,
                code="forbidden_role",
                message="This role cannot browse raw sources.",
                request_id=context.request_id,
                details={"role": context.role.value},
            )

        if source_type is not None and not is_source_type_allowed_for_role(
            source_type,
            actor_role=context.role,
            requested_domain=context.domain,
        ):
            raise ApiError(
                status_code=403,
                code="forbidden_scope",
                message="This role cannot browse that source type in the current domain.",
                request_id=context.request_id,
                details={"source_type": source_type.value},
            )

        source_records, total = list_sources(
            settings,
            course_id=context.course_id,
            class_id=context.class_id,
            actor_role=context.role,
            requested_domain=context.domain,
            source_type=source_type,
            q=q,
            limit=limit,
            offset=offset,
        )
        return success_response(
            context.request_id,
            [source_record_to_response_payload(source_record) for source_record in source_records],
            meta={"limit": limit, "offset": offset, "total": total},
        )

    @router.get("/{source_id}")
    def get_source_endpoint(
        source_id: str,
        context: Annotated[RequestContext, Depends(get_request_context)],
    ) -> dict[str, Any]:
        if context.role not in {
            ActorRole.INSTRUCTOR,
            ActorRole.OPERATOR,
            ActorRole.VALIDATOR,
            ActorRole.SYSTEM,
        }:
            raise ApiError(
                status_code=403,
                code="forbidden_role",
                message="This role cannot read raw source metadata.",
                request_id=context.request_id,
                details={"role": context.role.value},
            )

        try:
            source_record = get_source(settings, source_id)
        except SourceNotFoundError as exc:
            raise ApiError(
                status_code=404,
                code="not_found",
                message="Source was not found.",
                request_id=context.request_id,
                details={"source_id": source_id},
            ) from exc

        if (
            source_record.course_id != context.course_id
            or source_record.class_id != context.class_id
        ):
            raise ApiError(
                status_code=403,
                code="forbidden_scope",
                message="Source is outside the current course/class scope.",
                request_id=context.request_id,
                details={"source_id": source_id},
            )
        if not is_source_visible_to_role(
            source_record,
            actor_role=context.role,
            requested_domain=context.domain,
        ):
            raise ApiError(
                status_code=403,
                code="forbidden_scope",
                message="Source is outside the current role boundary.",
                request_id=context.request_id,
                details={"source_id": source_id},
            )

        return success_response(
            context.request_id,
            source_record_to_response_payload(source_record),
        )

    return router
