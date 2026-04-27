from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query

from knowloop_api.api.context import (
    RequestContext,
    get_mutating_review_request_context,
    get_review_request_context,
)
from knowloop_api.api.errors import ApiError, success_response
from knowloop_api.core.config import Settings
from knowloop_api.core.input_limits import MAX_CANDIDATE_ID_LENGTH
from knowloop_api.services.candidates import (
    CandidateKind,
    CandidateNotFoundError,
    CandidateStateError,
    CandidateStatus,
)
from knowloop_api.services.review import (
    ForbiddenReviewScopeError,
    ReviewApproveRequest,
    ReviewDropRequest,
    ReviewMergeRequest,
    ReviewPatchRequest,
    ReviewResumeSyncRequest,
    ReviewStateError,
    SourceIntegrityError,
    approve_candidate,
    drop_review_candidate,
    get_review_candidate_detail,
    list_review_candidates,
    merge_review_candidate,
    preview_candidate_patch,
    resume_candidate_sync,
)


def create_review_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/review", tags=["review"])

    @router.get("/candidates")
    def list_review_candidates_endpoint(
        context: Annotated[RequestContext, Depends(get_review_request_context)],
        status: Annotated[CandidateStatus | None, Query()] = CandidateStatus.OPEN,
        kind: Annotated[CandidateKind | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        try:
            candidates, total = list_review_candidates(
                settings,
                context=context,
                status=status,
                kind=kind,
                limit=limit,
                offset=offset,
            )
        except ForbiddenReviewScopeError as exc:
            raise ApiError(
                status_code=403,
                code="forbidden_scope",
                message=str(exc),
                request_id=context.request_id,
            ) from exc

        return success_response(
            context.request_id,
            candidates,
            meta={"limit": limit, "offset": offset, "total": total},
        )

    @router.get("/candidates/{candidate_id}")
    def get_review_candidate_endpoint(
        candidate_id: Annotated[str, Path(min_length=1, max_length=MAX_CANDIDATE_ID_LENGTH)],
        context: Annotated[RequestContext, Depends(get_review_request_context)],
    ) -> dict[str, Any]:
        try:
            detail = get_review_candidate_detail(
                settings,
                candidate_id=candidate_id,
                context=context,
            )
        except CandidateNotFoundError as exc:
            raise ApiError(
                status_code=404,
                code="not_found",
                message="Candidate was not found.",
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc
        except ForbiddenReviewScopeError as exc:
            raise ApiError(
                status_code=403,
                code="forbidden_scope",
                message=str(exc),
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc

        return success_response(
            context.request_id,
            detail.model_dump(mode="json"),
        )

    @router.post("/candidates/{candidate_id}/patch-preview")
    def preview_review_candidate_patch_endpoint(
        candidate_id: Annotated[str, Path(min_length=1, max_length=MAX_CANDIDATE_ID_LENGTH)],
        payload: ReviewPatchRequest,
        context: Annotated[RequestContext, Depends(get_review_request_context)],
    ) -> dict[str, Any]:
        try:
            preview = preview_candidate_patch(
                settings,
                candidate_id=candidate_id,
                payload=payload,
                context=context,
            )
        except CandidateNotFoundError as exc:
            raise ApiError(
                status_code=404,
                code="not_found",
                message="Candidate was not found.",
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc
        except ForbiddenReviewScopeError as exc:
            raise ApiError(
                status_code=403,
                code="forbidden_scope",
                message=str(exc),
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc
        except ReviewStateError as exc:
            raise ApiError(
                status_code=400,
                code="invalid_request",
                message=str(exc),
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc

        return success_response(context.request_id, preview.model_dump(mode="json"))

    @router.post("/candidates/{candidate_id}/approve")
    def approve_review_candidate_endpoint(
        candidate_id: Annotated[str, Path(min_length=1, max_length=MAX_CANDIDATE_ID_LENGTH)],
        payload: ReviewApproveRequest,
        context: Annotated[RequestContext, Depends(get_mutating_review_request_context)],
    ) -> dict[str, Any]:
        try:
            response = approve_candidate(
                settings,
                candidate_id=candidate_id,
                payload=payload,
                context=context,
            )
        except CandidateNotFoundError as exc:
            raise ApiError(
                status_code=404,
                code="not_found",
                message="Candidate was not found.",
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc
        except ForbiddenReviewScopeError as exc:
            raise ApiError(
                status_code=403,
                code="forbidden_scope",
                message=str(exc),
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc
        except SourceIntegrityError as exc:
            raise _source_integrity_error_to_api_error(
                exc,
                request_id=context.request_id,
            ) from exc
        except ReviewStateError as exc:
            raise ApiError(
                status_code=422,
                code="validation_failed",
                message=str(exc),
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc
        except CandidateStateError as exc:
            raise _candidate_state_error_to_api_error(
                exc,
                request_id=context.request_id,
                candidate_id=candidate_id,
            ) from exc

        return success_response(
            context.request_id,
            response.model_dump(mode="json", exclude_none=True),
        )

    @router.post("/candidates/{candidate_id}/merge")
    def merge_review_candidate_endpoint(
        candidate_id: Annotated[str, Path(min_length=1, max_length=MAX_CANDIDATE_ID_LENGTH)],
        payload: ReviewMergeRequest,
        context: Annotated[RequestContext, Depends(get_mutating_review_request_context)],
    ) -> dict[str, Any]:
        try:
            response = merge_review_candidate(
                settings,
                candidate_id=candidate_id,
                payload=payload,
                context=context,
            )
        except CandidateNotFoundError as exc:
            raise ApiError(
                status_code=404,
                code="not_found",
                message="Candidate was not found.",
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc
        except ForbiddenReviewScopeError as exc:
            raise ApiError(
                status_code=403,
                code="forbidden_scope",
                message=str(exc),
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc
        except ReviewStateError as exc:
            raise ApiError(
                status_code=422,
                code="validation_failed",
                message=str(exc),
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc
        except CandidateStateError as exc:
            raise _candidate_state_error_to_api_error(
                exc,
                request_id=context.request_id,
                candidate_id=candidate_id,
            ) from exc

        return success_response(
            context.request_id,
            response.model_dump(mode="json", exclude_none=True),
        )

    @router.post("/candidates/{candidate_id}/resume-sync")
    def resume_review_candidate_sync_endpoint(
        candidate_id: Annotated[str, Path(min_length=1, max_length=MAX_CANDIDATE_ID_LENGTH)],
        payload: ReviewResumeSyncRequest,
        context: Annotated[RequestContext, Depends(get_mutating_review_request_context)],
    ) -> dict[str, Any]:
        try:
            response = resume_candidate_sync(
                settings,
                candidate_id=candidate_id,
                payload=payload,
                context=context,
            )
        except CandidateNotFoundError as exc:
            raise ApiError(
                status_code=404,
                code="not_found",
                message="Candidate was not found.",
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc
        except ForbiddenReviewScopeError as exc:
            raise ApiError(
                status_code=403,
                code="forbidden_scope",
                message=str(exc),
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc
        except SourceIntegrityError as exc:
            raise _source_integrity_error_to_api_error(
                exc,
                request_id=context.request_id,
            ) from exc
        except ReviewStateError as exc:
            raise ApiError(
                status_code=422,
                code="validation_failed",
                message=str(exc),
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc
        except CandidateStateError as exc:
            raise _candidate_state_error_to_api_error(
                exc,
                request_id=context.request_id,
                candidate_id=candidate_id,
            ) from exc

        return success_response(
            context.request_id,
            response.model_dump(mode="json", exclude_none=True),
        )

    @router.post("/candidates/{candidate_id}/drop")
    def drop_review_candidate_endpoint(
        candidate_id: Annotated[str, Path(min_length=1, max_length=MAX_CANDIDATE_ID_LENGTH)],
        payload: ReviewDropRequest,
        context: Annotated[RequestContext, Depends(get_mutating_review_request_context)],
    ) -> dict[str, Any]:
        try:
            response = drop_review_candidate(
                settings,
                candidate_id=candidate_id,
                payload=payload,
                context=context,
            )
        except CandidateNotFoundError as exc:
            raise ApiError(
                status_code=404,
                code="not_found",
                message="Candidate was not found.",
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc
        except ForbiddenReviewScopeError as exc:
            raise ApiError(
                status_code=403,
                code="forbidden_scope",
                message=str(exc),
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc
        except ReviewStateError as exc:
            raise ApiError(
                status_code=422,
                code="validation_failed",
                message=str(exc),
                request_id=context.request_id,
                details={"candidate_id": candidate_id},
            ) from exc
        except CandidateStateError as exc:
            raise _candidate_state_error_to_api_error(
                exc,
                request_id=context.request_id,
                candidate_id=candidate_id,
            ) from exc

        return success_response(
            context.request_id,
            response.model_dump(mode="json", exclude_none=True),
        )

    return router


def _candidate_state_error_to_api_error(
    exc: CandidateStateError,
    *,
    request_id: str,
    candidate_id: str,
) -> ApiError:
    if "different request" in str(exc) or "stored approval plan" in str(exc):
        return ApiError(
            status_code=409,
            code="duplicate_action",
            message=str(exc),
            request_id=request_id,
            details={"candidate_id": candidate_id},
        )
    return ApiError(
        status_code=400,
        code="invalid_request",
        message=str(exc),
        request_id=request_id,
        details={"candidate_id": candidate_id},
    )


def _source_integrity_error_to_api_error(
    exc: SourceIntegrityError,
    *,
    request_id: str,
) -> ApiError:
    return ApiError(
        status_code=422,
        code="source_integrity_failed",
        message=str(exc),
        request_id=request_id,
        details={
            "candidate_id": exc.candidate_id,
            "source_id": exc.source_id,
            "ref_owner": exc.ref_owner,
            "reason": exc.reason,
        },
    )
