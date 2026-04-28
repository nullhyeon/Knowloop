from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from knowloop_api.api.context import RequestContext
from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole, RequestDomain
from knowloop_api.core.file_locks import (
    FileLockBusyError,
    acquire_file_lock,
    release_file_locks,
)
from knowloop_api.core.frontmatter import build_frontmatter_document
from knowloop_api.core.input_limits import (
    MAX_CANDIDATE_ID_LENGTH,
    MAX_REVIEW_NOTES_LENGTH,
    MAX_REVIEW_TARGET_PAGE_ID_LENGTH,
    MAX_REVIEW_TARGET_PATH_LENGTH,
)
from knowloop_api.db.audit import (
    begin_mutation_request,
    create_audit_event,
    get_mutation_request,
    list_audit_events,
    mark_mutation_request_applied,
    store_mutation_request_response_payload,
    update_audit_event_details,
)
from knowloop_api.services.candidates import (
    CandidateItem,
    CandidateKind,
    CandidateStateError,
    CandidateStatus,
    DropReason,
    WikiSyncStatus,
    drop_candidate,
    get_candidate,
    list_candidates_page,
    mark_candidate_wiki_synced,
    merge_candidate,
    promote_candidate,
)
from knowloop_api.services.sources import (
    SourceNotFoundError,
    SourceStateError,
    build_checksum,
    get_source,
    resolve_source_path,
)
from knowloop_api.services.wiki import build_wiki_page_path, get_wiki_page, load_wiki_page_from_path

ACADEMIC_REVIEW_KINDS = frozenset(
    {
        CandidateKind.MISCONCEPTION,
        CandidateKind.FAQ,
        CandidateKind.INTERVENTION,
        CandidateKind.UNRESOLVED_QUESTION,
    }
)
WIKI_SYNC_PENDING_ACTION = "candidate_wiki_sync_pending"
WIKI_SYNC_COMPLETED_ACTION = "candidate_wiki_synced"
RESUME_SYNC_REQUEST_ACTION = "candidate_wiki_sync_resumed"
WIKI_LOCK_STALE_AFTER = timedelta(minutes=5)
WIKI_DOMAIN_BY_KIND = {
    CandidateKind.FAQ: "faq",
    CandidateKind.MISCONCEPTION: "misconceptions",
    CandidateKind.INTERVENTION: "concepts",
    CandidateKind.UNRESOLVED_QUESTION: "concepts",
    CandidateKind.OPERATIONS_NOTE: "operations",
}
REVIEWABLE_ROLES = frozenset(
    {
        ActorRole.INSTRUCTOR,
        ActorRole.OPERATOR,
        ActorRole.VALIDATOR,
        ActorRole.SYSTEM,
    }
)


class ReviewStateError(ValueError):
    """Raised when a review request violates workflow expectations."""


class ReviewLockError(ReviewStateError):
    """Raised when wiki storage is temporarily locked by another writer."""


class SourceIntegrityError(ReviewStateError):
    """Raised when promotion evidence cannot be verified against raw sources."""

    def __init__(
        self,
        *,
        reason: str,
        source_id: str,
        ref_owner: str,
        candidate_id: str,
    ) -> None:
        super().__init__("Promotion source integrity check failed.")
        self.reason = reason
        self.source_id = source_id
        self.ref_owner = ref_owner
        self.candidate_id = candidate_id


class ForbiddenReviewScopeError(ReviewStateError):
    """Raised when the current role cannot access the requested review scope."""


class ReviewPatchRequest(BaseModel):
    target_page_id: str | None = Field(default=None, max_length=MAX_REVIEW_TARGET_PAGE_ID_LENGTH)
    target_path: str | None = Field(default=None, max_length=MAX_REVIEW_TARGET_PATH_LENGTH)
    notes: str | None = Field(default=None, max_length=MAX_REVIEW_NOTES_LENGTH)

    @model_validator(mode="after")
    def ensure_target_hint(self) -> "ReviewPatchRequest":
        if not self.target_page_id and not self.target_path:
            raise ValueError("target_page_id or target_path is required")
        return self


class ReviewApproveRequest(BaseModel):
    target_page_id: str | None = Field(default=None, max_length=MAX_REVIEW_TARGET_PAGE_ID_LENGTH)
    target_path: str | None = Field(default=None, max_length=MAX_REVIEW_TARGET_PATH_LENGTH)
    approval_notes: str | None = Field(default=None, max_length=MAX_REVIEW_NOTES_LENGTH)

    @model_validator(mode="after")
    def ensure_target_hint(self) -> "ReviewApproveRequest":
        if not self.target_page_id and not self.target_path:
            raise ValueError("target_page_id or target_path is required")
        return self


class ReviewMergeRequest(BaseModel):
    target_candidate_id: str = Field(min_length=1, max_length=MAX_CANDIDATE_ID_LENGTH)
    merge_notes: str | None = Field(default=None, max_length=MAX_REVIEW_NOTES_LENGTH)


class ReviewDropRequest(BaseModel):
    reason: DropReason
    drop_notes: str | None = Field(default=None, max_length=MAX_REVIEW_NOTES_LENGTH)


class ReviewResumeSyncRequest(BaseModel):
    resume_notes: str | None = Field(default=None, max_length=MAX_REVIEW_NOTES_LENGTH)


class ReviewCandidateDetail(BaseModel):
    candidate: dict[str, object]
    audit_events: list[dict[str, object]]
    available_actions: list[str]


class ReviewPatchPreview(BaseModel):
    candidate: dict[str, object]
    patch: dict[str, object]
    before_markdown: str | None = None
    after_markdown: str


class ReviewActionResponse(BaseModel):
    candidate: dict[str, object]
    patch: dict[str, object] | None = None
    target_candidate: dict[str, object] | None = None
    wiki_page: dict[str, object] | None = None


@dataclass(slots=True)
class WikiPatchDraft:
    patch_payload: dict[str, object]
    before_markdown: str | None
    after_markdown: str
    target_page_id: str
    target_path: Path
    operation: str


def list_review_candidates(
    settings: Settings,
    *,
    context: RequestContext,
    status: CandidateStatus | None = CandidateStatus.OPEN,
    kind: CandidateKind | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, object]], int]:
    _assert_review_role(context)
    candidates, total = list_candidates_page(
        settings,
        kind=kind,
        status=status,
        class_id=context.class_id,
        limit=limit,
        offset=offset,
        predicate=lambda candidate: (
            _is_candidate_visible(candidate, context=context)
            and candidate.course_id == context.course_id
        ),
    )
    return [candidate_to_payload(candidate) for candidate in candidates], total


def get_review_candidate_detail(
    settings: Settings,
    *,
    candidate_id: str,
    context: RequestContext,
) -> ReviewCandidateDetail:
    candidate = _load_visible_candidate(settings, candidate_id=candidate_id, context=context)
    audit_events = [
        {
            "event_id": event.event_id,
            "action": event.action,
            "actor_role": event.actor_role,
            "actor_id": event.actor_id,
            "from_status": event.from_status,
            "to_status": event.to_status,
            "notes": event.notes,
            "details": event.details,
            "request_id": event.request_id,
            "idempotency_key": event.idempotency_key,
            "created_at": event.created_at.isoformat().replace("+00:00", "Z"),
        }
        for event in list_audit_events(
            settings,
            entity_type="candidate",
            entity_id=candidate.candidate_id,
        )
    ]
    return ReviewCandidateDetail(
        candidate=candidate_to_payload(candidate),
        audit_events=audit_events,
        available_actions=_available_actions(candidate, context=context),
    )


def preview_candidate_patch(
    settings: Settings,
    *,
    candidate_id: str,
    payload: ReviewPatchRequest,
    context: RequestContext,
) -> ReviewPatchPreview:
    candidate = _load_visible_candidate(settings, candidate_id=candidate_id, context=context)
    patch_draft = _build_patch_draft(
        settings,
        candidate=candidate,
        context=context,
        target_page_id=payload.target_page_id,
        target_path=payload.target_path,
        notes=payload.notes,
        approval_status="draft",
        approved_by=None,
        approved_at=None,
    )
    return ReviewPatchPreview(
        candidate=candidate_to_payload(candidate),
        patch=patch_draft.patch_payload,
        before_markdown=patch_draft.before_markdown,
        after_markdown=patch_draft.after_markdown,
    )


def approve_candidate(
    settings: Settings,
    *,
    candidate_id: str,
    payload: ReviewApproveRequest,
    context: RequestContext,
) -> ReviewActionResponse:
    if context.idempotency_key is None or not context.idempotency_key.strip():
        raise ReviewStateError("Idempotency-Key is required for candidate approval")

    candidate = _load_visible_candidate(settings, candidate_id=candidate_id, context=context)
    target_page_id = payload.target_page_id or candidate.related_page_id
    if target_page_id is None:
        raise ReviewStateError("candidate approval requires a target_page_id")
    mutation_request = _get_candidate_transition_request(
        settings,
        candidate_id=candidate_id,
        action="candidate_promoted",
        idempotency_key=context.idempotency_key,
    )
    if mutation_request is None:
        _assert_action_allowed(candidate, context=context, action="approve")
    else:
        _assert_finalize_action_replay_allowed(candidate, context=context, action="approve")
    if mutation_request is None:
        canonical_target_path = _resolve_canonical_review_target_path(
            settings,
            candidate=candidate,
            target_page_id=target_page_id,
            target_path=payload.target_path,
            treat_scope_drift_as_plan_drift=False,
        )
        fingerprint_target_path = canonical_target_path
        approval_timestamp = datetime.now(UTC)
    else:
        canonical_target_path = _resolve_canonical_review_target_path(
            settings,
            candidate=candidate,
            target_page_id=target_page_id,
            target_path=None,
            treat_scope_drift_as_plan_drift=True,
        )
        if payload.target_path is None:
            fingerprint_target_path = canonical_target_path
        else:
            fingerprint_target_path = _normalize_review_target_path_input(
                settings,
                target_path=payload.target_path,
            )
        approval_timestamp = mutation_request.created_at
    patch_draft = _build_patch_draft(
        settings,
        candidate=candidate,
        context=context,
        target_page_id=target_page_id,
        target_path=canonical_target_path,
        notes=payload.approval_notes,
        approval_status="approved",
        approved_by=context.actor_id,
        approved_at=approval_timestamp,
        treat_scope_drift_as_plan_drift=mutation_request is not None,
        require_verified_source_refs=True,
    )
    approval_plan_fingerprint = _build_review_patch_fingerprint(
        settings,
        patch_draft=patch_draft,
    )
    promotion_attempt_id = candidate.promotion_attempt_id or _build_promotion_attempt_id(
        candidate_id=candidate.candidate_id,
        approved_at=approval_timestamp,
    )
    promoted_candidate = promote_candidate(
        settings,
        candidate_id,
        current_candidate_snapshot=candidate,
        approved_by=context.actor_id,
        actor_role=context.role,
        actor_id=context.actor_id,
        related_page_id=target_page_id,
        target_path=fingerprint_target_path,
        request_id=context.request_id,
        idempotency_key=context.idempotency_key,
        notes=payload.approval_notes,
        promotion_attempt_id=promotion_attempt_id,
        approval_plan_fingerprint=approval_plan_fingerprint,
        approved_at=approval_timestamp,
    )
    return _complete_candidate_wiki_sync(
        settings,
        candidate=promoted_candidate,
        patch_draft=patch_draft,
        context=context,
        notes=payload.approval_notes,
    )


def resume_candidate_sync(
    settings: Settings,
    *,
    candidate_id: str,
    payload: ReviewResumeSyncRequest,
    context: RequestContext,
) -> ReviewActionResponse:
    if context.idempotency_key is None or not context.idempotency_key.strip():
        raise ReviewStateError("Idempotency-Key is required for candidate sync resume")

    candidate = _load_visible_candidate(settings, candidate_id=candidate_id, context=context)
    mutation_request = _get_candidate_transition_request(
        settings,
        candidate_id=candidate_id,
        action=RESUME_SYNC_REQUEST_ACTION,
        idempotency_key=context.idempotency_key,
    )
    stored_resume_contract = (
        _extract_stored_resume_sync_contract(mutation_request)
        if mutation_request is not None
        else None
    )
    if mutation_request is not None:
        _assert_resume_sync_role_allowed(candidate, context=context)
        if stored_resume_contract is not None:
            resume_request_fingerprint = _build_resume_sync_request_fingerprint_from_contract(
                candidate_id=candidate.candidate_id,
                context=context,
                promotion_attempt_id=stored_resume_contract["promotion_attempt_id"],
                approval_plan_fingerprint=stored_resume_contract["approval_plan_fingerprint"],
                notes=payload.resume_notes,
            )
        else:
            if mutation_request.response_payload is not None:
                raise CandidateStateError(
                    "stored resumed candidate is missing a frozen replay contract"
                )
            resume_request_fingerprint = _build_resume_sync_request_fingerprint(
                candidate=candidate,
                context=context,
                notes=payload.resume_notes,
            )
        if mutation_request.request_fingerprint != resume_request_fingerprint:
            raise CandidateStateError("idempotency_key already exists for a different request")
        replayed_response = _finalize_or_replay_resume_sync(
            settings,
            mutation_request=mutation_request,
            candidate=candidate,
            context=context,
            notes=payload.resume_notes,
        )
        if replayed_response is not None:
            return replayed_response

    _assert_action_allowed(candidate, context=context, action="resume_sync")
    if candidate.related_page_id is None:
        raise ReviewStateError("pending candidate is missing related_page_id")
    if candidate.wiki_sync_target_path is None:
        raise ReviewStateError("pending candidate is missing wiki_sync_target_path")
    if candidate.approval_plan_fingerprint is None:
        raise ReviewStateError("pending candidate is missing approval_plan_fingerprint")
    if candidate.promotion_attempt_id is None:
        raise ReviewStateError("pending candidate is missing promotion_attempt_id")

    resume_request_fingerprint = _build_resume_sync_request_fingerprint(
        candidate=candidate,
        context=context,
        notes=payload.resume_notes,
    )
    if candidate.status is not CandidateStatus.PROMOTED:
        raise ReviewStateError("candidate sync resume requires a promoted candidate")
    if candidate.wiki_sync_status is not WikiSyncStatus.PENDING:
        raise ReviewStateError("candidate does not have a pending wiki sync")
    resume_contract = _resolve_resume_sync_contract(
        candidate=candidate,
        stored_resume_contract=stored_resume_contract,
    )

    patch_draft = _build_patch_draft(
        settings,
        candidate=candidate,
        context=context,
        target_page_id=candidate.related_page_id,
        target_path=candidate.wiki_sync_target_path,
        notes=payload.resume_notes,
        approval_status="approved",
        approved_by=candidate.approved_by,
        approved_at=candidate.approved_at,
        treat_scope_drift_as_plan_drift=True,
        require_verified_source_refs=True,
    )
    current_plan_fingerprint = _build_review_patch_fingerprint(
        settings,
        patch_draft=patch_draft,
    )
    if current_plan_fingerprint != resume_contract["approval_plan_fingerprint"]:
        raise CandidateStateError(
            "pending candidate sync no longer matches the stored approval plan"
        )

    if mutation_request is None:
        mutation_request = begin_mutation_request(
            settings,
            entity_type="candidate",
            entity_id=candidate_id,
            action=RESUME_SYNC_REQUEST_ACTION,
            idempotency_key=context.idempotency_key,
            actor_role=context.role.value,
            actor_id=context.actor_id,
            request_fingerprint=resume_request_fingerprint,
            created_at=datetime.now(UTC),
        )
        if mutation_request.request_fingerprint != resume_request_fingerprint:
            raise CandidateStateError("idempotency_key already exists for a different request")

    _ensure_candidate_wiki_sync_pending_audit(
        settings,
        candidate=candidate,
        context=context,
        audit_details=_require_wiki_sync_audit_details(
            candidate_id=candidate.candidate_id,
            promotion_attempt_id=resume_contract["promotion_attempt_id"],
            approval_plan_fingerprint=resume_contract["approval_plan_fingerprint"],
        ),
    )
    resume_sync_anchor = mutation_request.created_at

    def persist_resume_response(response: ReviewActionResponse, synced_at: datetime) -> None:
        response_payload = _build_resume_sync_response_payload(
            response=response,
            resume_contract=_build_resume_sync_contract(
                promotion_attempt_id=resume_contract["promotion_attempt_id"],
                approval_plan_fingerprint=resume_contract["approval_plan_fingerprint"],
            ),
        )
        store_mutation_request_response_payload(
            settings,
            entity_type="candidate",
            entity_id=candidate_id,
            action=RESUME_SYNC_REQUEST_ACTION,
            idempotency_key=context.idempotency_key,
            updated_at=synced_at,
            response_payload=response_payload,
        )

    def mark_resume_request_applied(response: ReviewActionResponse, synced_at: datetime) -> None:
        response_payload = _build_resume_sync_response_payload(
            response=response,
            resume_contract=_build_resume_sync_contract(
                promotion_attempt_id=resume_contract["promotion_attempt_id"],
                approval_plan_fingerprint=resume_contract["approval_plan_fingerprint"],
            ),
        )
        mark_mutation_request_applied(
            settings,
            entity_type="candidate",
            entity_id=candidate_id,
            action=RESUME_SYNC_REQUEST_ACTION,
            idempotency_key=context.idempotency_key,
            updated_at=synced_at,
            response_payload=response_payload,
        )

    response = _complete_candidate_wiki_sync(
        settings,
        candidate=candidate,
        patch_draft=patch_draft,
        context=context,
        notes=payload.resume_notes,
        emit_pending_audit=False,
        sync_anchor=resume_sync_anchor,
        persist_response_payload=persist_resume_response,
        mark_request_applied=mark_resume_request_applied,
    )
    return response


def merge_review_candidate(
    settings: Settings,
    *,
    candidate_id: str,
    payload: ReviewMergeRequest,
    context: RequestContext,
) -> ReviewActionResponse:
    if context.idempotency_key is None or not context.idempotency_key.strip():
        raise ReviewStateError("Idempotency-Key is required for candidate merge")

    source_candidate = _load_visible_candidate(settings, candidate_id=candidate_id, context=context)
    mutation_request = _get_candidate_transition_request(
        settings,
        candidate_id=candidate_id,
        action="candidate_merged",
        idempotency_key=context.idempotency_key,
    )
    if mutation_request is None:
        _assert_action_allowed(source_candidate, context=context, action="merge")
    else:
        _assert_finalize_action_replay_allowed(
            source_candidate,
            context=context,
            action="merge",
        )
    target_candidate = _load_visible_candidate(
        settings,
        candidate_id=payload.target_candidate_id,
        context=context,
    )
    merged_candidate = merge_candidate(
        settings,
        candidate_id,
        target_candidate_id=target_candidate.candidate_id,
        actor_role=context.role,
        actor_id=context.actor_id,
        request_id=context.request_id,
        idempotency_key=context.idempotency_key,
        notes=payload.merge_notes,
    )
    refreshed_target = get_candidate(settings, target_candidate.candidate_id)
    return ReviewActionResponse(
        candidate=candidate_to_payload(merged_candidate),
        target_candidate=candidate_to_payload(refreshed_target),
    )


def drop_review_candidate(
    settings: Settings,
    *,
    candidate_id: str,
    payload: ReviewDropRequest,
    context: RequestContext,
) -> ReviewActionResponse:
    if context.idempotency_key is None or not context.idempotency_key.strip():
        raise ReviewStateError("Idempotency-Key is required for candidate drop")

    candidate = _load_visible_candidate(settings, candidate_id=candidate_id, context=context)
    mutation_request = _get_candidate_transition_request(
        settings,
        candidate_id=candidate_id,
        action="candidate_dropped",
        idempotency_key=context.idempotency_key,
    )
    if mutation_request is None:
        _assert_action_allowed(candidate, context=context, action="drop")
    else:
        _assert_finalize_action_replay_allowed(candidate, context=context, action="drop")
    notes = _format_drop_notes(reason=payload.reason, drop_notes=payload.drop_notes)
    dropped_candidate = drop_candidate(
        settings,
        candidate_id,
        actor_role=context.role,
        actor_id=context.actor_id,
        request_id=context.request_id,
        idempotency_key=context.idempotency_key,
        reason=payload.reason,
        notes=notes,
    )
    return ReviewActionResponse(
        candidate=candidate_to_payload(dropped_candidate),
    )


def candidate_to_payload(candidate: CandidateItem) -> dict[str, object]:
    payload = candidate.model_dump(mode="json", exclude_none=True)
    payload["review_domain"] = _candidate_review_domain(candidate).value
    return payload


def _load_visible_candidate(
    settings: Settings,
    *,
    candidate_id: str,
    context: RequestContext,
) -> CandidateItem:
    _assert_review_role(context)
    candidate = get_candidate(settings, candidate_id)
    if candidate.course_id != context.course_id or candidate.class_id != context.class_id:
        raise ForbiddenReviewScopeError("Candidate is outside the current course/class scope.")
    if not _is_candidate_visible(candidate, context=context):
        raise ForbiddenReviewScopeError("Candidate is outside the current role boundary.")
    return candidate


def _assert_review_role(context: RequestContext) -> None:
    if context.role not in REVIEWABLE_ROLES:
        raise ForbiddenReviewScopeError("This role cannot access the review workflow.")
    expected_domain = {
        ActorRole.INSTRUCTOR: RequestDomain.ACADEMIC,
        ActorRole.OPERATOR: RequestDomain.OPERATIONS,
        ActorRole.VALIDATOR: RequestDomain.REVIEW,
        ActorRole.SYSTEM: RequestDomain.REVIEW,
    }[context.role]
    if context.domain is not expected_domain:
        raise ForbiddenReviewScopeError(
            f"This role must use the {expected_domain.value} domain for review workflows."
        )


def _is_candidate_visible(candidate: CandidateItem, *, context: RequestContext) -> bool:
    candidate_domain = _candidate_review_domain(candidate)
    if context.role is ActorRole.SYSTEM:
        return True
    if context.role is ActorRole.VALIDATOR:
        return True
    if context.role is ActorRole.INSTRUCTOR:
        return candidate_domain is RequestDomain.ACADEMIC
    if context.role is ActorRole.OPERATOR:
        return candidate_domain is RequestDomain.OPERATIONS
    return False


def _available_actions(candidate: CandidateItem, *, context: RequestContext) -> list[str]:
    if context.role not in REVIEWABLE_ROLES:
        return []
    if not _is_candidate_visible(candidate, context=context):
        return []
    if (
        candidate.status is CandidateStatus.PROMOTED
        and candidate.wiki_sync_status is WikiSyncStatus.PENDING
    ):
        if _can_finalize_candidate(candidate, context=context):
            return ["resume_sync"]
        if context.role is ActorRole.SYSTEM:
            return ["patch_preview"]
        return []
    if candidate.status is not CandidateStatus.OPEN:
        return []
    if not _can_finalize_candidate(candidate, context=context):
        return ["patch_preview"]
    return ["patch_preview", "approve", "merge", "drop"]


def _can_finalize_candidate(candidate: CandidateItem, *, context: RequestContext) -> bool:
    if context.role is ActorRole.SYSTEM:
        return False
    if context.role is ActorRole.OPERATOR:
        return False
    if (
        context.role is ActorRole.INSTRUCTOR
        and _candidate_review_domain(candidate) is RequestDomain.OPERATIONS
    ):
        return False
    return True


def _assert_action_allowed(
    candidate: CandidateItem,
    *,
    context: RequestContext,
    action: str,
) -> None:
    if action == "resume_sync":
        if (
            candidate.status is not CandidateStatus.PROMOTED
            or candidate.wiki_sync_status is not WikiSyncStatus.PENDING
        ):
            raise ForbiddenReviewScopeError(
                "This candidate does not have a resumable wiki sync in the current scope."
            )
        if not _can_finalize_candidate(candidate, context=context):
            raise ForbiddenReviewScopeError(
                f"This role cannot {action} candidates in the current scope."
            )
        return
    if candidate.status is not CandidateStatus.OPEN:
        raise ForbiddenReviewScopeError(
            f"This candidate is not open for {action} in the current scope."
        )
    if not _can_finalize_candidate(candidate, context=context):
        raise ForbiddenReviewScopeError(
            f"This role cannot {action} candidates in the current scope."
        )


def _assert_resume_sync_role_allowed(
    candidate: CandidateItem,
    *,
    context: RequestContext,
) -> None:
    if not _is_candidate_visible(candidate, context=context):
        raise ForbiddenReviewScopeError(
            "This candidate is not visible in the current review scope."
        )
    if not _can_finalize_candidate(candidate, context=context):
        raise ForbiddenReviewScopeError(
            "This role cannot resume_sync candidates in the current scope."
        )


def _assert_finalize_action_replay_allowed(
    candidate: CandidateItem,
    *,
    context: RequestContext,
    action: str,
) -> None:
    if not _is_candidate_visible(candidate, context=context):
        raise ForbiddenReviewScopeError(
            f"This candidate is not visible for {action} replay in the current scope."
        )
    if not _can_finalize_candidate(candidate, context=context):
        raise ForbiddenReviewScopeError(
            f"This role cannot {action} candidates in the current scope."
        )


def _candidate_review_domain(candidate: CandidateItem) -> RequestDomain:
    if candidate.kind in ACADEMIC_REVIEW_KINDS:
        return RequestDomain.ACADEMIC
    return RequestDomain.OPERATIONS


def _build_patch_draft(
    settings: Settings,
    *,
    candidate: CandidateItem,
    context: RequestContext,
    target_page_id: str | None,
    target_path: str | None,
    notes: str | None,
    approval_status: str,
    approved_by: str | None,
    approved_at: datetime | None,
    treat_scope_drift_as_plan_drift: bool = False,
    require_verified_source_refs: bool = False,
) -> WikiPatchDraft:
    target_page_id = target_page_id or candidate.related_page_id
    if target_page_id is None:
        raise ReviewStateError("candidate approval requires a target_page_id")

    domain_name = WIKI_DOMAIN_BY_KIND[candidate.kind]
    existing_page = get_wiki_page(
        settings,
        target_page_id,
        course_id=candidate.course_id,
        class_id=candidate.class_id,
    )
    _assert_existing_page_in_review_scope(
        candidate,
        existing_page,
        treat_scope_drift_as_plan_drift=treat_scope_drift_as_plan_drift,
    )
    resolved_path = _resolve_target_path(
        settings,
        domain_name=domain_name,
        course_id=candidate.course_id,
        class_scope=candidate.class_id,
        target_page_id=target_page_id,
        target_path=target_path,
        existing_page_path=Path(existing_page.path) if existing_page is not None else None,
        treat_scope_drift_as_plan_drift=treat_scope_drift_as_plan_drift,
    )
    before_markdown = resolved_path.read_text(encoding="utf-8") if resolved_path.exists() else None
    if before_markdown is None and existing_page is not None:
        before_markdown = Path(existing_page.path).read_text(encoding="utf-8")
        resolved_path = Path(existing_page.path)

    page_title = existing_page.title if existing_page is not None else _derive_page_title(candidate)
    summary = existing_page.summary if existing_page is not None else candidate.summary
    source_ids = _merge_unique_strings(
        existing_page.source_refs if existing_page is not None else [],
        [source_ref.source_id for source_ref in candidate.source_refs],
    )
    if require_verified_source_refs:
        _verify_wiki_metadata_source_refs(
            settings,
            candidate=candidate,
            source_ids=source_ids,
        )
    candidate_refs = _merge_unique_strings(
        existing_page.candidate_refs if existing_page is not None else [],
        [candidate.candidate_id],
    )
    source_contents = _load_source_contents(
        settings,
        candidate,
        require_verified_source_refs=require_verified_source_refs,
    )
    body_markdown, change_plan = _build_body_markdown(
        candidate=candidate,
        page_title=page_title,
        existing_body=existing_page.body_markdown if existing_page is not None else None,
        source_contents=source_contents,
    )
    effective_updated_at = approved_at or datetime.now(UTC)
    wiki_metadata = {
        "page_id": target_page_id,
        "domain": domain_name,
        "title": page_title,
        "course_id": candidate.course_id,
        "class_scope": candidate.class_id,
        "updated_at": effective_updated_at.isoformat().replace("+00:00", "Z"),
        "source_refs": source_ids,
        "candidate_refs": candidate_refs,
        "summary": summary,
    }
    after_markdown = build_frontmatter_document(wiki_metadata, body_markdown)
    patch_payload = {
        "target_page_id": target_page_id,
        "target_path": _as_data_relative_path(settings, resolved_path),
        "operation": "update" if resolved_path.exists() else "create",
        "title": page_title,
        "summary": summary,
        "domain": domain_name,
        "course_id": candidate.course_id,
        "class_id": candidate.class_id,
        "actor_role": context.role.value,
        "change_plan": change_plan,
        "source_refs": [
            source_ref.model_dump(mode="json", exclude_none=True)
            for source_ref in candidate.source_refs
        ],
        "candidate_refs": candidate_refs,
        "created_at": effective_updated_at.isoformat().replace("+00:00", "Z"),
        "approval_status": approval_status,
    }
    if approved_by is not None:
        patch_payload["approved_by"] = approved_by
    if approved_at is not None:
        patch_payload["approved_at"] = approved_at.isoformat().replace("+00:00", "Z")

    return WikiPatchDraft(
        patch_payload=patch_payload,
        before_markdown=before_markdown,
        after_markdown=after_markdown,
        target_page_id=target_page_id,
        target_path=resolved_path,
        operation=patch_payload["operation"],
    )


def _resolve_canonical_review_target_path(
    settings: Settings,
    *,
    candidate: CandidateItem,
    target_page_id: str,
    target_path: str | None,
    treat_scope_drift_as_plan_drift: bool = False,
) -> str:
    domain_name = WIKI_DOMAIN_BY_KIND[candidate.kind]
    existing_page = get_wiki_page(
        settings,
        target_page_id,
        course_id=candidate.course_id,
        class_id=candidate.class_id,
    )
    _assert_existing_page_in_review_scope(
        candidate,
        existing_page,
        treat_scope_drift_as_plan_drift=treat_scope_drift_as_plan_drift,
    )
    resolved_path = _resolve_target_path(
        settings,
        domain_name=domain_name,
        course_id=candidate.course_id,
        class_scope=candidate.class_id,
        target_page_id=target_page_id,
        target_path=target_path,
        existing_page_path=Path(existing_page.path) if existing_page is not None else None,
        treat_scope_drift_as_plan_drift=treat_scope_drift_as_plan_drift,
    )
    return _as_data_relative_path(settings, resolved_path)


def _normalize_review_target_path_input(
    settings: Settings,
    *,
    target_path: str | None,
) -> str | None:
    if target_path is None:
        return None

    candidate_path = Path(target_path)
    if candidate_path.parts[:1] == ("data",):
        return candidate_path.as_posix()

    if candidate_path.is_absolute():
        try:
            return _as_data_relative_path(settings, candidate_path)
        except ValueError:
            return candidate_path.as_posix()

    return (Path("data") / candidate_path).as_posix()


def _assert_existing_page_in_review_scope(
    candidate: CandidateItem,
    existing_page,
    *,
    treat_scope_drift_as_plan_drift: bool = False,
) -> None:
    if existing_page is None:
        return
    if (
        existing_page.course_id != candidate.course_id
        or existing_page.class_scope != candidate.class_id
    ):
        if treat_scope_drift_as_plan_drift:
            raise CandidateStateError(
                "pending candidate sync no longer matches the stored approval plan"
            )
        raise ReviewStateError(
            "target_page_id must belong to the same course_id and class_id as the candidate"
        )


def _build_review_patch_fingerprint(
    settings: Settings,
    *,
    patch_draft: WikiPatchDraft,
) -> str:
    payload = {
        "page_id": patch_draft.target_page_id,
        "target_path": _as_data_relative_path(settings, patch_draft.target_path),
        "operation": patch_draft.operation,
        "patch": patch_draft.patch_payload,
        "after_markdown": patch_draft.after_markdown,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _build_promotion_attempt_id(*, candidate_id: str, approved_at: datetime) -> str:
    timestamp = approved_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"pat-{candidate_id}-{timestamp}"


def _build_resume_sync_request_fingerprint(
    *,
    candidate: CandidateItem,
    context: RequestContext,
    notes: str | None,
) -> str:
    if candidate.promotion_attempt_id is None:
        raise ReviewStateError("pending candidate is missing promotion_attempt_id")
    if candidate.approval_plan_fingerprint is None:
        raise ReviewStateError("pending candidate is missing approval_plan_fingerprint")
    return _build_review_request_fingerprint(
        candidate_id=candidate.candidate_id,
        action=RESUME_SYNC_REQUEST_ACTION,
        actor_role=context.role.value,
        actor_id=context.actor_id,
        promotion_attempt_id=candidate.promotion_attempt_id,
        approval_plan_fingerprint=candidate.approval_plan_fingerprint,
        notes=notes,
    )


def _build_resume_sync_request_fingerprint_from_contract(
    *,
    candidate_id: str,
    context: RequestContext,
    promotion_attempt_id: str,
    approval_plan_fingerprint: str,
    notes: str | None,
) -> str:
    return _build_review_request_fingerprint(
        candidate_id=candidate_id,
        action=RESUME_SYNC_REQUEST_ACTION,
        actor_role=context.role.value,
        actor_id=context.actor_id,
        promotion_attempt_id=promotion_attempt_id,
        approval_plan_fingerprint=approval_plan_fingerprint,
        notes=notes,
    )


def _build_resume_sync_response_payload(
    *,
    response: ReviewActionResponse,
    base_payload: dict[str, object] | None = None,
    resume_contract: dict[str, str] | None = None,
) -> dict[str, object]:
    payload = (
        dict(base_payload)
        if isinstance(base_payload, dict)
        else response.model_dump(mode="json", exclude_none=True)
    )
    if resume_contract is not None:
        payload["_resume_contract"] = dict(resume_contract)
    return payload


def _extract_stored_resume_sync_contract(mutation_request) -> dict[str, str] | None:
    response_payload = mutation_request.response_payload
    if not isinstance(response_payload, dict):
        return None
    return _extract_resume_sync_contract_from_payload(response_payload)


def _extract_resume_sync_contract_from_payload(
    response_payload: dict[str, object],
) -> dict[str, str] | None:
    contract = response_payload.get("_resume_contract")
    if not isinstance(contract, dict):
        candidate_payload = response_payload.get("candidate")
        if isinstance(candidate_payload, dict):
            contract = {
                "promotion_attempt_id": candidate_payload.get("promotion_attempt_id"),
                "approval_plan_fingerprint": candidate_payload.get(
                    "approval_plan_fingerprint"
                ),
            }
        else:
            return None

    promotion_attempt_id = contract.get("promotion_attempt_id")
    approval_plan_fingerprint = contract.get("approval_plan_fingerprint")
    if not isinstance(promotion_attempt_id, str) or not promotion_attempt_id:
        return None
    if not isinstance(approval_plan_fingerprint, str) or not approval_plan_fingerprint:
        return None
    return {
        "promotion_attempt_id": promotion_attempt_id,
        "approval_plan_fingerprint": approval_plan_fingerprint,
    }


def _resolve_resume_sync_replay_synced_at(
    *,
    response: ReviewActionResponse,
    fallback: datetime,
) -> datetime:
    if response.candidate is not None:
        synced_at = response.candidate.get("wiki_synced_at")
        if isinstance(synced_at, str) and synced_at:
            try:
                return datetime.fromisoformat(synced_at.replace("Z", "+00:00")).astimezone(UTC)
            except ValueError:
                pass
    return fallback


def _build_review_request_fingerprint(**payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _finalize_or_replay_resume_sync(
    settings: Settings,
    *,
    mutation_request,
    candidate: CandidateItem,
    context: RequestContext,
    notes: str | None,
) -> ReviewActionResponse | None:
    if mutation_request.response_payload is not None:
        stored_resume_contract = _extract_stored_resume_sync_contract(mutation_request)
        response = ReviewActionResponse.model_validate(mutation_request.response_payload)
        response_payload = _build_resume_sync_response_payload(
            response=response,
            base_payload=(
                mutation_request.response_payload
                if isinstance(mutation_request.response_payload, dict)
                else None
            ),
            resume_contract=stored_resume_contract,
        )
        if mutation_request.status == "applied":
            repaired_candidate = candidate
            if (
                candidate.status is CandidateStatus.PROMOTED
                and candidate.wiki_sync_status is not WikiSyncStatus.SYNCED
            ):
                repaired_candidate = mark_candidate_wiki_synced(
                    settings,
                    candidate.candidate_id,
                    synced_at=_resolve_resume_sync_replay_synced_at(
                        response=response,
                        fallback=mutation_request.updated_at,
                    ),
                )
            if (
                repaired_candidate.status is CandidateStatus.PROMOTED
                and repaired_candidate.wiki_sync_status is WikiSyncStatus.SYNCED
                and stored_resume_contract is not None
            ):
                _, wiki_patch_created_at, synced_created_at = _build_wiki_sync_audit_timestamps(
                    mutation_request.created_at
                )
                audit_details = _require_wiki_sync_audit_details(
                    candidate_id=repaired_candidate.candidate_id,
                    promotion_attempt_id=stored_resume_contract["promotion_attempt_id"],
                    approval_plan_fingerprint=stored_resume_contract[
                        "approval_plan_fingerprint"
                    ],
                )
                _ensure_candidate_wiki_sync_pending_audit(
                    settings,
                    candidate=repaired_candidate,
                    context=context,
                    audit_details=audit_details,
                )
                replay_page_id = None
                if response.wiki_page is not None:
                    replay_page_id = response.wiki_page.get("page_id")
                if not isinstance(replay_page_id, str) or not replay_page_id:
                    replay_page_id = repaired_candidate.related_page_id
                if replay_page_id is not None:
                    _record_wiki_patch_applied(
                        settings,
                        page_id=replay_page_id,
                        context=context,
                        created_at=wiki_patch_created_at,
                        notes=notes,
                        audit_details=audit_details,
                    )
                _record_candidate_wiki_synced(
                    settings,
                    candidate_id=repaired_candidate.candidate_id,
                    context=context,
                    created_at=synced_created_at,
                    audit_details=audit_details,
                )
            if mutation_request.response_payload != response_payload:
                store_mutation_request_response_payload(
                    settings,
                    entity_type="candidate",
                    entity_id=repaired_candidate.candidate_id,
                    action=RESUME_SYNC_REQUEST_ACTION,
                    idempotency_key=context.idempotency_key,
                    updated_at=mutation_request.updated_at,
                    response_payload=response_payload,
                )
            return response
        if (
            candidate.status is CandidateStatus.PROMOTED
            and candidate.wiki_sync_status is WikiSyncStatus.SYNCED
        ):
            audit_details = _require_wiki_sync_audit_details(
                candidate_id=candidate.candidate_id,
                promotion_attempt_id=(
                    stored_resume_contract["promotion_attempt_id"]
                    if stored_resume_contract is not None
                    else candidate.promotion_attempt_id
                ),
                approval_plan_fingerprint=(
                    stored_resume_contract["approval_plan_fingerprint"]
                    if stored_resume_contract is not None
                    else candidate.approval_plan_fingerprint
                ),
            )
            _, _, synced_created_at = _build_wiki_sync_audit_timestamps(mutation_request.created_at)
            _record_candidate_wiki_synced(
                settings,
                candidate_id=candidate.candidate_id,
                context=context,
                created_at=synced_created_at,
                audit_details=audit_details,
            )
            if mutation_request.response_payload != response_payload:
                store_mutation_request_response_payload(
                    settings,
                    entity_type="candidate",
                    entity_id=candidate.candidate_id,
                    action=RESUME_SYNC_REQUEST_ACTION,
                    idempotency_key=context.idempotency_key,
                    updated_at=candidate.wiki_synced_at or synced_created_at,
                    response_payload=response_payload,
                )
            if mutation_request.status != "applied":
                mark_mutation_request_applied(
                    settings,
                    entity_type="candidate",
                    entity_id=candidate.candidate_id,
                    action=RESUME_SYNC_REQUEST_ACTION,
                    idempotency_key=context.idempotency_key,
                    updated_at=candidate.wiki_synced_at or synced_created_at,
                    response_payload=response_payload,
                )
            return response
    if (
        candidate.status is CandidateStatus.PROMOTED
        and candidate.wiki_sync_status is WikiSyncStatus.SYNCED
    ):
        raise CandidateStateError("stored resumed candidate does not match the idempotent request")
    if mutation_request.status != "applied":
        return None
    if mutation_request.status == "applied":
        raise CandidateStateError("stored resumed candidate does not match the idempotent request")
    return None


def _complete_candidate_wiki_sync(
    settings: Settings,
    *,
    candidate: CandidateItem,
    patch_draft: WikiPatchDraft,
    context: RequestContext,
    notes: str | None,
    emit_pending_audit: bool = True,
    sync_anchor: datetime | None = None,
    persist_response_payload=None,
    mark_request_applied=None,
) -> ReviewActionResponse:
    pending_created_at, wiki_patch_created_at, synced_created_at = (
        _build_wiki_sync_audit_timestamps(
            sync_anchor or candidate.approved_at
        )
    )
    predicted_synced_candidate = candidate.model_copy(
        update={
            "wiki_sync_status": WikiSyncStatus.SYNCED,
            "wiki_synced_at": synced_created_at,
            "updated_at": synced_created_at,
        }
    )
    response = ReviewActionResponse(
        candidate=candidate_to_payload(predicted_synced_candidate),
        patch=patch_draft.patch_payload,
        wiki_page={
            "page_id": patch_draft.target_page_id,
            "path": _as_data_relative_path(settings, patch_draft.target_path),
            "operation": patch_draft.operation,
            "updated_at": synced_created_at.isoformat().replace("+00:00", "Z"),
        },
    )
    if persist_response_payload is not None:
        persist_response_payload(response, synced_created_at)
    if emit_pending_audit:
        _record_candidate_wiki_sync_pending(
            settings,
            candidate_id=candidate.candidate_id,
            context=context,
            created_at=pending_created_at,
            audit_details=_require_wiki_sync_audit_details(
                candidate_id=candidate.candidate_id,
                promotion_attempt_id=candidate.promotion_attempt_id,
                approval_plan_fingerprint=candidate.approval_plan_fingerprint,
            ),
        )
    _apply_wiki_patch_atomically(patch_draft)
    _record_wiki_patch_applied(
        settings,
        page_id=patch_draft.target_page_id,
        context=context,
        created_at=wiki_patch_created_at,
        notes=notes,
        audit_details=_require_wiki_sync_audit_details(
            candidate_id=candidate.candidate_id,
            promotion_attempt_id=candidate.promotion_attempt_id,
            approval_plan_fingerprint=candidate.approval_plan_fingerprint,
        ),
    )
    synced_candidate = mark_candidate_wiki_synced(
        settings,
        candidate.candidate_id,
        synced_at=synced_created_at,
    )
    _record_candidate_wiki_synced(
        settings,
        candidate_id=synced_candidate.candidate_id,
        context=context,
        created_at=synced_created_at,
        audit_details=_require_wiki_sync_audit_details(
            candidate_id=synced_candidate.candidate_id,
            promotion_attempt_id=synced_candidate.promotion_attempt_id,
            approval_plan_fingerprint=synced_candidate.approval_plan_fingerprint,
        ),
    )
    response = response.model_copy(update={"candidate": candidate_to_payload(synced_candidate)})
    if mark_request_applied is not None:
        mark_request_applied(response, synced_created_at)
    return response


def _build_wiki_sync_audit_timestamps(
    approved_at: datetime | None,
) -> tuple[datetime, datetime, datetime]:
    anchor = approved_at or datetime.now(UTC)
    return (
        anchor + timedelta(microseconds=1),
        anchor + timedelta(microseconds=2),
        anchor + timedelta(microseconds=3),
    )


def _get_candidate_transition_request(
    settings: Settings,
    *,
    candidate_id: str,
    action: str,
    idempotency_key: str | None,
):
    if idempotency_key is None:
        return None
    return get_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=candidate_id,
        action=action,
        idempotency_key=idempotency_key,
    )


def _record_candidate_wiki_sync_pending(
    settings: Settings,
    *,
    candidate_id: str,
    context: RequestContext,
    created_at: datetime | None,
    audit_details: dict[str, str] | None = None,
) -> None:
    if _ensure_candidate_owned_wiki_sync_audit_event(
        settings,
        entity_id=candidate_id,
        action=WIKI_SYNC_PENDING_ACTION,
        details=audit_details,
    ):
        return
    create_audit_event(
        settings,
        entity_type="candidate",
        entity_id=candidate_id,
        action=WIKI_SYNC_PENDING_ACTION,
        actor_role=context.role.value,
        actor_id=context.actor_id,
        request_id=context.request_id,
        idempotency_key=context.idempotency_key,
        created_at=created_at,
        notes="Candidate promotion is waiting for wiki patch application.",
        details=audit_details,
    )


def _ensure_candidate_wiki_sync_pending_audit(
    settings: Settings,
    *,
    candidate: CandidateItem,
    context: RequestContext,
    audit_details: dict[str, str] | None = None,
) -> None:
    effective_audit_details = audit_details or _require_wiki_sync_audit_details(
        candidate_id=candidate.candidate_id,
        promotion_attempt_id=candidate.promotion_attempt_id,
        approval_plan_fingerprint=candidate.approval_plan_fingerprint,
    )
    if _ensure_candidate_owned_wiki_sync_audit_event(
        settings,
        entity_id=candidate.candidate_id,
        action=WIKI_SYNC_PENDING_ACTION,
        details=effective_audit_details,
    ):
        return

    pending_created_at, _, _ = _build_wiki_sync_audit_timestamps(candidate.approved_at)
    promotion_audits = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
    )
    source_audit = promotion_audits[0] if promotion_audits else None
    create_audit_event(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action=WIKI_SYNC_PENDING_ACTION,
        actor_role=source_audit.actor_role if source_audit is not None else context.role.value,
        actor_id=source_audit.actor_id if source_audit is not None else context.actor_id,
        request_id=source_audit.request_id if source_audit is not None else context.request_id,
        idempotency_key=source_audit.idempotency_key if source_audit is not None else None,
        created_at=pending_created_at,
        notes="Candidate promotion is waiting for wiki patch application.",
        details=effective_audit_details,
    )


def _record_wiki_patch_applied(
    settings: Settings,
    *,
    page_id: str,
    context: RequestContext,
    created_at: datetime | None,
    notes: str | None,
    audit_details: dict[str, str] | None = None,
) -> None:
    if _ensure_page_owned_wiki_patch_audit_event(
        settings,
        page_id=page_id,
        details=audit_details,
        idempotency_key=context.idempotency_key,
    ):
        return
    create_audit_event(
        settings,
        entity_type="wiki_page",
        entity_id=page_id,
        action="wiki_patch_applied",
        actor_role=context.role.value,
        actor_id=context.actor_id,
        request_id=context.request_id,
        idempotency_key=context.idempotency_key,
        created_at=created_at,
        notes=notes,
        details=audit_details,
    )


def _record_candidate_wiki_synced(
    settings: Settings,
    *,
    candidate_id: str,
    context: RequestContext,
    created_at: datetime | None,
    audit_details: dict[str, str] | None = None,
) -> None:
    if _ensure_candidate_owned_wiki_sync_audit_event(
        settings,
        entity_id=candidate_id,
        action=WIKI_SYNC_COMPLETED_ACTION,
        details=audit_details,
    ):
        return
    create_audit_event(
        settings,
        entity_type="candidate",
        entity_id=candidate_id,
        action=WIKI_SYNC_COMPLETED_ACTION,
        actor_role=context.role.value,
        actor_id=context.actor_id,
        request_id=context.request_id,
        idempotency_key=context.idempotency_key,
        created_at=created_at,
        notes="Candidate promotion has been synchronized into the formal wiki.",
        details=audit_details,
    )


def _find_matching_structured_wiki_sync_event(
    settings: Settings,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    details: dict[str, str],
):
    existing_events = list_audit_events(
        settings,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
    )
    for event in existing_events:
        if not isinstance(event.details, dict):
            continue
        if all(event.details.get(key) == value for key, value in details.items()):
            return event
    return None


def _find_matching_page_owned_wiki_patch_event(
    settings: Settings,
    *,
    page_id: str,
    details: dict[str, str],
    idempotency_key: str | None,
):
    existing_events = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id=page_id,
        action="wiki_patch_applied",
        idempotency_key=idempotency_key,
    )
    for event in existing_events:
        if not isinstance(event.details, dict):
            continue
        if all(event.details.get(key) == value for key, value in details.items()):
            return event
    return None


def _ensure_candidate_owned_wiki_sync_audit_event(
    settings: Settings,
    *,
    entity_id: str,
    action: str,
    details: dict[str, str] | None,
) -> bool:
    if details is None:
        return bool(
            list_audit_events(
                settings,
                entity_type="candidate",
                entity_id=entity_id,
                action=action,
            )
        )

    matching_event = _find_matching_structured_wiki_sync_event(
        settings,
        entity_type="candidate",
        entity_id=entity_id,
        action=action,
        details=details,
    )
    if matching_event is not None:
        return True

    existing_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=entity_id,
        action=action,
    )
    if not existing_events:
        return False
    legacy_events = [event for event in existing_events if not isinstance(event.details, dict)]
    if (
        len(legacy_events) == 1
        and len(existing_events) == 1
        and _candidate_owned_wiki_sync_chain_is_unique(
            settings,
            candidate_id=entity_id,
            action=action,
        )
    ):
        update_audit_event_details(
            settings,
            event_id=legacy_events[0].event_id,
            details=details,
        )
        return True
    return False


def _ensure_page_owned_wiki_patch_audit_event(
    settings: Settings,
    *,
    page_id: str,
    details: dict[str, str] | None,
    idempotency_key: str | None,
) -> bool:
    if details is None:
        return bool(
            list_audit_events(
                settings,
                entity_type="wiki_page",
                entity_id=page_id,
                action="wiki_patch_applied",
            )
        )

    matching_event = _find_matching_page_owned_wiki_patch_event(
        settings,
        page_id=page_id,
        details=details,
        idempotency_key=idempotency_key,
    )
    if matching_event is not None:
        return True

    existing_events = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id=page_id,
        action="wiki_patch_applied",
    )
    if not existing_events:
        return False

    legacy_events = [event for event in existing_events if not isinstance(event.details, dict)]
    if len(legacy_events) == 1 and len(existing_events) == 1:
        legacy_event = legacy_events[0]
        if legacy_event.idempotency_key == idempotency_key and _can_upgrade_legacy_page_audit(
            settings,
            details=details,
            idempotency_key=idempotency_key,
        ):
            update_audit_event_details(
                settings,
                event_id=legacy_event.event_id,
                details=details,
            )
            return True
    return False


def _can_upgrade_legacy_page_audit(
    settings: Settings,
    *,
    details: dict[str, str],
    idempotency_key: str | None,
) -> bool:
    if idempotency_key is None:
        return False
    candidate_id = details.get("candidate_id")
    if candidate_id is None:
        return False
    matching_candidate_events = [
        event
        for action in (WIKI_SYNC_PENDING_ACTION, WIKI_SYNC_COMPLETED_ACTION)
        for event in list_audit_events(
            settings,
            entity_type="candidate",
            entity_id=candidate_id,
            action=action,
            idempotency_key=idempotency_key,
        )
        if isinstance(event.details, dict)
        and all(event.details.get(key) == value for key, value in details.items())
    ]
    return len(matching_candidate_events) >= 1


def _build_wiki_sync_audit_details(
    *,
    candidate_id: str,
    promotion_attempt_id: str | None,
    approval_plan_fingerprint: str | None,
) -> dict[str, str]:
    details = {"candidate_id": candidate_id}
    if promotion_attempt_id is not None:
        details["promotion_attempt_id"] = promotion_attempt_id
    if approval_plan_fingerprint is not None:
        details["approval_plan_fingerprint"] = approval_plan_fingerprint
    return details


def _build_resume_sync_contract(
    *,
    promotion_attempt_id: str | None,
    approval_plan_fingerprint: str | None,
) -> dict[str, str]:
    if promotion_attempt_id is None:
        raise ReviewStateError("resume sync replay contract requires promotion_attempt_id")
    if approval_plan_fingerprint is None:
        raise ReviewStateError("resume sync replay contract requires approval_plan_fingerprint")
    return {
        "promotion_attempt_id": promotion_attempt_id,
        "approval_plan_fingerprint": approval_plan_fingerprint,
    }


def _resolve_resume_sync_contract(
    *,
    candidate: CandidateItem,
    stored_resume_contract: dict[str, str] | None,
) -> dict[str, str]:
    if stored_resume_contract is not None:
        return stored_resume_contract
    return _build_resume_sync_contract(
        promotion_attempt_id=candidate.promotion_attempt_id,
        approval_plan_fingerprint=candidate.approval_plan_fingerprint,
    )


def _candidate_owned_wiki_sync_chain_is_unique(
    settings: Settings,
    *,
    candidate_id: str,
    action: str,
) -> bool:
    pending_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate_id,
        action=WIKI_SYNC_PENDING_ACTION,
    )
    synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate_id,
        action=WIKI_SYNC_COMPLETED_ACTION,
    )
    if action == WIKI_SYNC_PENDING_ACTION:
        return len(pending_events) == 1 and len(synced_events) <= 1
    if action == WIKI_SYNC_COMPLETED_ACTION:
        return len(pending_events) == 1 and len(synced_events) == 1
    return False


def _require_wiki_sync_audit_details(
    *,
    candidate_id: str,
    promotion_attempt_id: str | None,
    approval_plan_fingerprint: str | None,
) -> dict[str, str]:
    if promotion_attempt_id is None:
        raise ReviewStateError("wiki sync audit details require promotion_attempt_id")
    if approval_plan_fingerprint is None:
        raise ReviewStateError("wiki sync audit details require approval_plan_fingerprint")
    return _build_wiki_sync_audit_details(
        candidate_id=candidate_id,
        promotion_attempt_id=promotion_attempt_id,
        approval_plan_fingerprint=approval_plan_fingerprint,
    )


def _apply_wiki_patch_atomically(patch_draft: WikiPatchDraft) -> None:
    lock_path = _acquire_wiki_lock(patch_draft.target_path)
    try:
        current_contents = (
            patch_draft.target_path.read_text(encoding="utf-8")
            if patch_draft.target_path.exists()
            else None
        )
        if current_contents != patch_draft.before_markdown:
            raise ReviewStateError("wiki page changed before the approval patch could be applied")
        _write_wiki_page(patch_draft.target_path, patch_draft.after_markdown)
    finally:
        release_file_locks([lock_path])


def _acquire_wiki_lock(target_path: Path) -> Path:
    try:
        return acquire_file_lock(
            target_path,
            stale_after=WIKI_LOCK_STALE_AFTER,
        )
    except FileLockBusyError as exc:
        raise ReviewLockError("wiki storage is busy, retry later") from exc


def _format_drop_notes(*, reason: str, drop_notes: str | None) -> str:
    normalized_reason = reason.strip()
    if drop_notes is None or not drop_notes.strip():
        return f"Drop reason: {normalized_reason}"
    normalized_notes = drop_notes.strip()
    return f"Drop reason: {normalized_reason}\nDrop notes: {normalized_notes}"


def _resolve_target_path(
    settings: Settings,
    *,
    domain_name: str,
    course_id: str,
    class_scope: str,
    target_page_id: str,
    target_path: str | None,
    existing_page_path: Path | None,
    treat_scope_drift_as_plan_drift: bool = False,
) -> Path:
    slug_prefix = f"page-{domain_name}-"
    if not target_page_id.startswith(slug_prefix) or target_page_id == slug_prefix:
        raise ReviewStateError(
            f"target_page_id must match the page-{domain_name}-<slug> contract"
        )

    try:
        canonical_path = build_wiki_page_path(
            settings,
            domain=domain_name,
            class_scope=class_scope,
            page_id=target_page_id,
        ).resolve()
    except ValueError as exc:
        raise ReviewStateError(str(exc)) from exc

    if existing_page_path is not None:
        resolved_existing_path = existing_page_path.resolve()
        if resolved_existing_path != canonical_path:
            if treat_scope_drift_as_plan_drift:
                raise CandidateStateError(
                    "pending candidate sync no longer matches the stored approval plan"
                )
            raise ReviewStateError("existing wiki page is stored outside the canonical scoped path")

    if canonical_path.exists():
        try:
            canonical_page = load_wiki_page_from_path(canonical_path)
        except (KeyError, OSError, ValueError) as exc:
            if treat_scope_drift_as_plan_drift:
                raise CandidateStateError(
                    "pending candidate sync no longer matches the stored approval plan"
                ) from exc
            raise ReviewStateError(
                "stored wiki page at the canonical path could not be read"
            ) from exc
        if (
            canonical_page.page_id != target_page_id
            or canonical_page.domain != domain_name
            or canonical_page.course_id != course_id
            or canonical_page.class_scope != class_scope
        ):
            if treat_scope_drift_as_plan_drift:
                raise CandidateStateError(
                    "pending candidate sync no longer matches the stored approval plan"
                )
            raise ReviewStateError(
                "stored wiki page at the canonical path does not match the requested scope"
            )

    if target_path:
        candidate_path = Path(target_path)
        if candidate_path.parts[:1] == ("data",):
            candidate_path = settings.data_root / Path(*candidate_path.parts[1:])
        elif not candidate_path.is_absolute():
            candidate_path = settings.data_root / candidate_path
        resolved_path = candidate_path.resolve()
        if resolved_path != canonical_path:
            raise ReviewStateError(
                "target_path must match the canonical wiki path for target_page_id"
            )
    else:
        resolved_path = canonical_path

    wiki_root = (settings.data_root / "wiki").resolve()
    try:
        resolved_path.relative_to(wiki_root)
    except ValueError as exc:
        raise ReviewStateError("target_path escapes the configured wiki root") from exc
    return resolved_path


def _load_source_contents(
    settings: Settings,
    candidate: CandidateItem,
    *,
    require_verified_source_refs: bool = False,
) -> list[str]:
    contents: list[str] = []
    for source_ref in candidate.source_refs:
        if require_verified_source_refs:
            contents.append(
                _read_verified_source_contents(
                    settings,
                    candidate=candidate,
                    source_id=source_ref.source_id,
                    ref_owner="candidate",
                    expected_source_type=source_ref.source_type,
                )
            )
            continue
        try:
            source_record = get_source(settings, source_ref.source_id)
            source_path = resolve_source_path(settings, source_record.origin_path)
            if not source_path.exists():
                continue
            contents.append(source_path.read_text(encoding="utf-8"))
        except (OSError, SourceNotFoundError, SourceStateError, UnicodeDecodeError):
            continue
    return contents


def _verify_wiki_metadata_source_refs(
    settings: Settings,
    *,
    candidate: CandidateItem,
    source_ids: list[str],
) -> None:
    candidate_source_types = {
        source_ref.source_id: source_ref.source_type for source_ref in candidate.source_refs
    }
    for source_id in source_ids:
        ref_owner = "candidate" if source_id in candidate_source_types else "wiki_page"
        _read_verified_source_contents(
            settings,
            candidate=candidate,
            source_id=source_id,
            ref_owner=ref_owner,
            expected_source_type=candidate_source_types.get(source_id),
        )


def _read_verified_source_contents(
    settings: Settings,
    *,
    candidate: CandidateItem,
    source_id: str,
    ref_owner: str,
    expected_source_type: str | None,
) -> str:
    try:
        source_record = get_source(settings, source_id)
    except SourceNotFoundError as exc:
        raise SourceIntegrityError(
            reason="source_ref_unresolved",
            source_id=source_id,
            ref_owner=ref_owner,
            candidate_id=candidate.candidate_id,
        ) from exc
    try:
        source_path = resolve_source_path(settings, source_record.origin_path)
    except SourceStateError as exc:
        raise SourceIntegrityError(
            reason="source_file_path_invalid",
            source_id=source_id,
            ref_owner=ref_owner,
            candidate_id=candidate.candidate_id,
        ) from exc
    if not source_path.is_file():
        raise SourceIntegrityError(
            reason="source_file_missing",
            source_id=source_id,
            ref_owner=ref_owner,
            candidate_id=candidate.candidate_id,
        )
    try:
        source_contents = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SourceIntegrityError(
            reason="source_file_unreadable",
            source_id=source_id,
            ref_owner=ref_owner,
            candidate_id=candidate.candidate_id,
        ) from exc
    _assert_source_ref_matches_candidate(
        candidate,
        source_id=source_id,
        ref_owner=ref_owner,
        source_record=source_record,
        source_contents=source_contents,
        expected_source_type=expected_source_type,
    )
    return source_contents


def _raise_source_integrity_error(
    *,
    reason: str,
    source_id: str,
    ref_owner: str,
    candidate_id: str,
) -> None:
    raise SourceIntegrityError(
        reason=reason,
        source_id=source_id,
        ref_owner=ref_owner,
        candidate_id=candidate_id,
    )


def _assert_source_ref_matches_candidate(
    candidate: CandidateItem,
    *,
    source_id: str,
    ref_owner: str,
    source_record,
    source_contents: str,
    expected_source_type: str | None,
) -> None:
    if (
        source_record.course_id != candidate.course_id
        or source_record.class_id != candidate.class_id
    ):
        _raise_source_integrity_error(
            reason="source_scope_mismatch",
            source_id=source_id,
            ref_owner=ref_owner,
            candidate_id=candidate.candidate_id,
        )
    if source_record.domain is not _candidate_review_domain(candidate):
        _raise_source_integrity_error(
            reason="source_domain_mismatch",
            source_id=source_id,
            ref_owner=ref_owner,
            candidate_id=candidate.candidate_id,
        )
    if expected_source_type is not None and source_record.source_type.value != expected_source_type:
        _raise_source_integrity_error(
            reason="source_type_mismatch",
            source_id=source_id,
            ref_owner=ref_owner,
            candidate_id=candidate.candidate_id,
        )
    if build_checksum(source_contents) != source_record.checksum:
        _raise_source_integrity_error(
            reason="source_checksum_mismatch",
            source_id=source_id,
            ref_owner=ref_owner,
            candidate_id=candidate.candidate_id,
        )


def _build_body_markdown(
    *,
    candidate: CandidateItem,
    page_title: str,
    existing_body: str | None,
    source_contents: list[str],
) -> tuple[str, list[str]]:
    if candidate.kind is CandidateKind.FAQ:
        return _build_faq_body(
            candidate=candidate,
            page_title=page_title,
            existing_body=existing_body,
            source_contents=source_contents,
        )
    return _build_generic_body(
        candidate=candidate,
        page_title=page_title,
        existing_body=existing_body,
    )


def _build_faq_body(
    *,
    candidate: CandidateItem,
    page_title: str,
    existing_body: str | None,
    source_contents: list[str],
) -> tuple[str, list[str]]:
    combined_sentences = _extract_sentences(
        "\n\n".join(filter(None, [existing_body, *source_contents]))
    )
    submit_sentence = _pick_sentence(combined_sentences, keywords=("submit", "lms"))
    deadline_sentence = _pick_sentence(combined_sentences, keywords=("due", "deadline"))
    late_sentence = _pick_sentence(combined_sentences, keywords=("late", "accommodation"))

    change_plan = [
        "Review and apply the structured FAQ candidate to the formal wiki page.",
    ]
    lines = [f"# {page_title}"]

    if submit_sentence:
        lines.extend(["", submit_sentence])
        change_plan.append("Keep LMS submission instructions at the top of the page.")
    else:
        lines.extend(["", candidate.summary])

    if deadline_sentence:
        lines.extend(["", "## Deadline", "", deadline_sentence])
        change_plan.append("Clarify the deadline in a dedicated section.")

    if late_sentence:
        lines.extend(["", "## Late policy", "", late_sentence])
        change_plan.append("Document the late policy for quick review.")

    body_markdown = "\n".join(lines).strip() + "\n"
    return body_markdown, change_plan


def _build_generic_body(
    *,
    candidate: CandidateItem,
    page_title: str,
    existing_body: str | None,
) -> tuple[str, list[str]]:
    if existing_body:
        return existing_body.strip() + "\n", [
            "Preserve the existing reviewed page body while linking the approved candidate.",
        ]

    lines = [
        f"# {page_title}",
        "",
        candidate.summary,
    ]
    if candidate.kind is CandidateKind.MISCONCEPTION:
        lines.extend(
            [
                "",
                "## What students are mixing up",
                "",
                candidate.summary,
            ]
        )
    return "\n".join(lines).strip() + "\n", [
        "Create a new reviewed wiki page from the candidate summary.",
    ]


def _pick_sentence(sentences: list[str], *, keywords: tuple[str, ...]) -> str | None:
    for sentence in sentences:
        lowered = sentence.lower()
        if any(keyword in lowered for keyword in keywords):
            return sentence
    return None


def _extract_sentences(contents: str) -> list[str]:
    normalized = contents.replace("\r\n", "\n")
    chunks = [chunk.strip() for chunk in normalized.splitlines() if chunk.strip()]
    sentences: list[str] = []
    for chunk in chunks:
        if chunk.startswith("#"):
            continue
        if chunk.startswith("---"):
            continue
        sentences.append(chunk)
    return _dedupe_preserve_order(sentences)


def _derive_page_title(candidate: CandidateItem) -> str:
    if candidate.kind is CandidateKind.FAQ and "homework" in candidate.title.lower():
        return "Homework Submission"
    return candidate.title


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item in seen:
            continue
        deduped.append(item)
        seen.add(item)
    return deduped


def _merge_unique_strings(base: list[str], extra: list[str]) -> list[str]:
    merged = list(base)
    seen = set(base)
    for item in extra:
        if item in seen:
            continue
        merged.append(item)
        seen.add(item)
    return merged


def _write_wiki_page(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def _as_data_relative_path(settings: Settings, path: Path) -> str:
    resolved_path = path.resolve()
    data_root = settings.data_root.resolve()
    relative_path = resolved_path.relative_to(data_root)
    return (Path("data") / relative_path).as_posix()
