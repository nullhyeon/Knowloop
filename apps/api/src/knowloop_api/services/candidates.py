from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole
from knowloop_api.core.file_locks import (
    FileLockBusyError,
    acquire_file_locks,
    release_file_locks,
)
from knowloop_api.core.pagination import collect_descending_page
from knowloop_api.db.audit import (
    begin_mutation_request,
    create_audit_event,
    list_audit_events,
    list_mutation_requests,
    mark_mutation_request_applied,
    store_mutation_request_response_payload,
)


class CandidateKind(StrEnum):
    MISCONCEPTION = "misconception"
    FAQ = "faq"
    INTERVENTION = "intervention"
    UNRESOLVED_QUESTION = "unresolved_question"
    OPERATIONS_NOTE = "operations_note"


class CandidateStatus(StrEnum):
    OPEN = "open"
    PROMOTED = "promoted"
    MERGED = "merged"
    DROPPED = "dropped"


class WikiSyncStatus(StrEnum):
    PENDING = "pending"
    SYNCED = "synced"


class DropReason(StrEnum):
    INSUFFICIENT_SHARED_VALUE = "insufficient_shared_value"
    OBSOLETE_OPERATIONS_SIGNAL = "obsolete_operations_signal"
    SUPERSEDED_BY_EXISTING_CANDIDATE = "superseded_by_existing_candidate"


class SourceRef(BaseModel):
    source_id: str
    source_type: str
    chunk_id: str | None = None


class CandidateItem(BaseModel):
    candidate_id: str
    kind: CandidateKind
    status: CandidateStatus
    title: str
    summary: str
    class_id: str
    course_id: str
    actor_role: ActorRole | None = None
    confidence: float = Field(ge=0, le=1)
    tags: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(min_length=1)
    session_refs: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    approved_by: str | None = None
    approved_at: datetime | None = None
    merged_into: str | None = None
    related_page_id: str | None = None
    promotion_attempt_id: str | None = None
    wiki_sync_target_path: str | None = None
    approval_plan_fingerprint: str | None = None
    wiki_sync_status: WikiSyncStatus | None = None
    wiki_synced_at: datetime | None = None

class CandidateNotFoundError(FileNotFoundError):
    """Raised when a candidate file cannot be located."""


class CandidateStateError(ValueError):
    """Raised when a candidate transition is invalid."""


class CandidateLockError(CandidateStateError):
    """Raised when candidate storage is temporarily locked by another writer."""


CANDIDATE_KIND_DIRECTORIES = {
    CandidateKind.MISCONCEPTION: "misconceptions",
    CandidateKind.FAQ: "faq",
    CandidateKind.INTERVENTION: "interventions",
    CandidateKind.UNRESOLVED_QUESTION: "unresolved-questions",
    CandidateKind.OPERATIONS_NOTE: "operations-notes",
}

PROMOTION_PAGE_PREFIXES = {
    CandidateKind.FAQ: "page-faq-",
    CandidateKind.MISCONCEPTION: "page-misconceptions-",
    CandidateKind.OPERATIONS_NOTE: "page-operations-",
}

CREATE_REQUEST_ENTITY_TYPE = "candidate_registration"
CREATE_REQUEST_ENTITY_ID = "candidate_store"
CREATE_ACTION = "candidate_created"
UPSERT_ACTION = "candidate_signal_upserted"
CANDIDATE_LOCK_STALE_AFTER = timedelta(minutes=5)


def create_candidate(
    settings: Settings,
    candidate: CandidateItem,
    *,
    actor_role: ActorRole,
    actor_id: str | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    notes: str | None = None,
) -> CandidateItem:
    if candidate.status is not CandidateStatus.OPEN:
        raise CandidateStateError("new candidates must start in the open state")
    if candidate.actor_role is not None and candidate.actor_role is not actor_role:
        raise CandidateStateError("candidate actor_role must match the creating actor role")

    candidate = candidate.model_copy(
        update={
            "actor_role": actor_role,
            "updated_at": candidate.updated_at,
        }
    )
    mutation_request = _begin_create_candidate_request(
        settings,
        candidate=candidate,
        actor_role=actor_role,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    replayed_candidate = _finalize_or_replay_create_candidate(
        settings,
        mutation_request=mutation_request,
        idempotency_key=idempotency_key,
    )
    if replayed_candidate is not None:
        return replayed_candidate
    mutation_request = _ensure_create_candidate_request_intent(
        settings,
        mutation_request=mutation_request,
        candidate=candidate,
        idempotency_key=idempotency_key,
    )
    candidate = _apply_create_request_intent(candidate, mutation_request=mutation_request)
    recovered_candidate = _recover_create_candidate_without_audit(
        settings,
        mutation_request=mutation_request,
        requested_candidate=candidate,
        actor_role=actor_role,
        actor_id=actor_id,
        request_id=request_id,
        idempotency_key=idempotency_key,
        notes=notes,
    )
    if recovered_candidate is not None:
        return recovered_candidate

    candidate_path = build_candidate_path(settings, candidate)
    existing_candidate = _find_existing_candidate(settings, candidate.candidate_id)
    if existing_candidate is not None:
        if existing_candidate == candidate:
            if _has_competing_pending_create_requests(
                settings,
                mutation_request=mutation_request,
                idempotency_key=idempotency_key,
                ):
                raise CandidateStateError(
                    "candidate already exists under another pending request"
                )
            if idempotency_key is not None and _candidate_belongs_to_other_create_lineage(
                settings,
                candidate_id=existing_candidate.candidate_id,
                idempotency_key=idempotency_key,
            ):
                raise CandidateStateError(
                    "stored created candidate does not match the idempotent request"
                )
            _ensure_candidate_created_audit(
                settings,
                candidate=existing_candidate,
                actor_role=actor_role,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                notes=notes,
            )
            _mark_create_candidate_applied(
                settings,
                idempotency_key=idempotency_key,
                updated_at=datetime.now(UTC),
            )
            return existing_candidate
        raise FileExistsError(f"candidate already exists: {candidate.candidate_id}")

    _apply_candidate_transaction(
        {
            candidate_path: candidate,
        },
        expected_current={
            candidate_path: None,
        },
        persist_audit=lambda: create_audit_event(
            settings,
            entity_type="candidate",
            entity_id=candidate.candidate_id,
            action=CREATE_ACTION,
            actor_role=actor_role.value,
            actor_id=actor_id,
            from_status=None,
            to_status=candidate.status.value,
            notes=notes,
            request_id=request_id,
            idempotency_key=idempotency_key,
            created_at=candidate.created_at,
        ),
        mark_applied=lambda: _mark_create_candidate_applied(
            settings,
            idempotency_key=idempotency_key,
            updated_at=candidate.created_at,
        ),
    )
    return candidate


def upsert_candidate_signal(
    settings: Settings,
    candidate: CandidateItem,
    *,
    actor_role: ActorRole,
    actor_id: str | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    notes: str | None = None,
    allow_match_by_metadata: bool = True,
) -> tuple[CandidateItem, str]:
    existing_candidate = _find_existing_candidate(settings, candidate.candidate_id)
    if existing_candidate is not None and existing_candidate.status is not CandidateStatus.OPEN:
        existing_candidate = None
    if existing_candidate is None and allow_match_by_metadata:
        existing_candidate = _find_matching_open_candidate(settings, candidate)
    if existing_candidate is None:
        created = create_candidate(
            settings,
            candidate,
            actor_role=actor_role,
            actor_id=actor_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            notes=notes,
        )
        return created, "create"

    merged_candidate = existing_candidate.model_copy(
        update={
            "tags": _merge_unique_strings(existing_candidate.tags, candidate.tags),
            "source_refs": _merge_source_refs(
                existing_candidate.source_refs,
                candidate.source_refs,
            ),
            "session_refs": _merge_unique_strings(
                existing_candidate.session_refs,
                candidate.session_refs,
            ),
            "confidence": max(existing_candidate.confidence, candidate.confidence),
            "summary": candidate.summary or existing_candidate.summary,
            "related_page_id": existing_candidate.related_page_id or candidate.related_page_id,
            "actor_role": existing_candidate.actor_role or actor_role,
        }
    )
    if merged_candidate == existing_candidate:
        candidate_action = (
            "create" if existing_candidate.candidate_id == candidate.candidate_id else "update"
        )
        return existing_candidate, candidate_action
    updated_candidate = merged_candidate.model_copy(
        update={
            "updated_at": datetime.now(UTC),
        }
    )

    candidate_path = find_candidate_path(settings, existing_candidate.candidate_id)
    _apply_candidate_transaction(
        {
            candidate_path: updated_candidate,
        },
        expected_current={
            candidate_path: existing_candidate,
        },
        persist_audit=lambda: create_audit_event(
            settings,
            entity_type="candidate",
            entity_id=existing_candidate.candidate_id,
            action=UPSERT_ACTION,
            actor_role=actor_role.value,
            actor_id=actor_id,
            from_status=existing_candidate.status.value,
            to_status=updated_candidate.status.value,
            notes=notes or "Merged new query signal into an existing open candidate.",
            details={
                "proposed_candidate_id": candidate.candidate_id,
                "target_id": existing_candidate.candidate_id,
            },
            request_id=request_id,
            idempotency_key=idempotency_key,
            created_at=datetime.now(UTC),
        ),
    )
    return updated_candidate, "update"


def get_candidate(settings: Settings, candidate_id: str) -> CandidateItem:
    candidate_path = find_candidate_path(settings, candidate_id)
    return _load_candidate_file(candidate_path)


def list_candidates(
    settings: Settings,
    *,
    kind: CandidateKind | None = None,
    status: CandidateStatus | None = None,
    class_id: str | None = None,
) -> list[CandidateItem]:
    return sorted(
        iter_candidates(
            settings,
            kind=kind,
            status=status,
            class_id=class_id,
        ),
        key=_candidate_sort_key,
        reverse=True,
    )


def list_candidates_page(
    settings: Settings,
    *,
    kind: CandidateKind | None = None,
    status: CandidateStatus | None = None,
    class_id: str | None = None,
    limit: int,
    offset: int = 0,
    predicate: Callable[[CandidateItem], bool] | None = None,
) -> tuple[list[CandidateItem], int]:
    candidates = iter_candidates(
        settings,
        kind=kind,
        status=status,
        class_id=class_id,
    )
    if predicate is not None:
        candidates = (candidate for candidate in candidates if predicate(candidate))
    return collect_descending_page(
        candidates,
        key=_candidate_sort_key,
        limit=limit,
        offset=offset,
    )


def iter_candidates(
    settings: Settings,
    *,
    kind: CandidateKind | None = None,
    status: CandidateStatus | None = None,
    class_id: str | None = None,
) -> Iterator[CandidateItem]:
    candidate_root = settings.data_root / "candidate"
    if not candidate_root.exists():
        return

    for path in _iter_candidate_paths(
        candidate_root,
        kind=kind,
        class_id=class_id,
    ):
        candidate = _load_candidate_file(path)
        if kind is not None and candidate.kind is not kind:
            continue
        if status is not None and candidate.status is not status:
            continue
        if class_id is not None and candidate.class_id != class_id:
            continue
        yield candidate


def _candidate_sort_key(candidate: CandidateItem) -> tuple[datetime, datetime, str]:
    return candidate.updated_at, candidate.created_at, candidate.candidate_id


def _iter_candidate_paths(
    candidate_root: Path,
    *,
    kind: CandidateKind | None,
    class_id: str | None,
) -> Iterator[Path]:
    for root, pattern in _build_candidate_search_scopes(
        candidate_root,
        kind=kind,
        class_id=class_id,
    ):
        if not root.exists():
            continue
        yield from sorted(root.glob(pattern))


def _build_candidate_search_scopes(
    candidate_root: Path,
    *,
    kind: CandidateKind | None,
    class_id: str | None,
) -> list[tuple[Path, str]]:
    if kind is not None:
        kind_root = candidate_root / CANDIDATE_KIND_DIRECTORIES[kind]
        if class_id is not None:
            return [(kind_root / class_id, "*.json")]
        return [(kind_root, "*/*.json")]

    if class_id is not None:
        return [
            (candidate_root / kind_directory / class_id, "*.json")
            for kind_directory in CANDIDATE_KIND_DIRECTORIES.values()
        ]

    return [
        (candidate_root / kind_directory, "*/*.json")
        for kind_directory in CANDIDATE_KIND_DIRECTORIES.values()
    ]


def promote_candidate(
    settings: Settings,
    candidate_id: str,
    *,
    current_candidate_snapshot: CandidateItem | None = None,
    approved_by: str,
    actor_role: ActorRole,
    actor_id: str | None = None,
    related_page_id: str | None = None,
    target_path: str | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    notes: str | None = None,
    promotion_attempt_id: str | None = None,
    approval_plan_fingerprint: str | None = None,
    approved_at: datetime | None = None,
) -> CandidateItem:
    current_candidate = current_candidate_snapshot or get_candidate(settings, candidate_id)
    _assert_review_authorized(
        current_candidate,
        actor_role=actor_role,
        action="candidate_promoted",
    )
    _assert_approver_identity(approved_by=approved_by, actor_id=actor_id)

    transition_at = approved_at or datetime.now(UTC)
    target_page_id = related_page_id or current_candidate.related_page_id
    if target_page_id is None:
        raise CandidateStateError("promoted candidates must reference a target wiki page")
    _assert_promotion_target(current_candidate, target_page_id=target_page_id)

    updated_candidate = current_candidate.model_copy(
        update={
            "status": CandidateStatus.PROMOTED,
            "approved_by": approved_by,
            "approved_at": transition_at,
            "related_page_id": target_page_id,
            "promotion_attempt_id": promotion_attempt_id or current_candidate.promotion_attempt_id,
            "wiki_sync_target_path": target_path or current_candidate.wiki_sync_target_path,
            "approval_plan_fingerprint": (
                approval_plan_fingerprint or current_candidate.approval_plan_fingerprint
            ),
            "wiki_sync_status": WikiSyncStatus.PENDING,
            "wiki_synced_at": None,
            "updated_at": transition_at,
        }
    )
    request_fingerprint_payload = {
        "candidate_id": candidate_id,
        "action": "candidate_promoted",
        "actor_role": actor_role,
        "actor_id": actor_id,
        "approved_by": approved_by,
        "related_page_id": target_page_id,
        "requested_approved_at": _serialize_optional_timestamp(approved_at),
        "notes": notes,
    }
    if target_path is not None:
        request_fingerprint_payload["target_path"] = target_path
    if approval_plan_fingerprint is not None:
        request_fingerprint_payload["approval_plan_fingerprint"] = approval_plan_fingerprint

    mutation_request = _begin_transition_request(
        settings,
        entity_id=candidate_id,
        action="candidate_promoted",
        actor_role=actor_role,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        request_fingerprint=_build_request_fingerprint(**request_fingerprint_payload),
        created_at=transition_at,
    )
    replayed_candidate = _finalize_or_replay_promote(
        settings,
        mutation_request=mutation_request,
        current_candidate=current_candidate,
        expected_candidate=updated_candidate,
        actor_role=actor_role,
        actor_id=actor_id,
        request_id=request_id,
        idempotency_key=idempotency_key,
        notes=notes,
    )
    if replayed_candidate is not None:
        return replayed_candidate

    _assert_status(current_candidate, expected=CandidateStatus.OPEN)
    candidate_path = find_candidate_path(settings, candidate_id)
    try:
        _apply_candidate_transaction(
            {
                candidate_path: updated_candidate,
            },
            expected_current={
                candidate_path: current_candidate,
            },
            persist_audit=lambda: create_audit_event(
                settings,
                entity_type="candidate",
                entity_id=candidate_id,
                action="candidate_promoted",
                actor_role=actor_role.value,
                actor_id=actor_id,
                from_status=current_candidate.status.value,
                to_status=updated_candidate.status.value,
                notes=notes,
                request_id=request_id,
                idempotency_key=idempotency_key,
                created_at=transition_at,
            ),
            mark_applied=lambda: _mark_transition_applied(
                settings,
                entity_id=candidate_id,
                action="candidate_promoted",
                idempotency_key=idempotency_key,
                updated_at=transition_at,
            ),
        )
    except CandidateStateError as exc:
        replayed_candidate = _retry_changed_transition(
            exc,
            current_candidate_loader=lambda: get_candidate(settings, candidate_id),
            finalize=lambda latest_candidate: _finalize_or_replay_promote(
                settings,
                mutation_request=mutation_request,
                current_candidate=latest_candidate,
                expected_candidate=updated_candidate,
                actor_role=actor_role,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                notes=notes,
            ),
        )
        if replayed_candidate is not None:
            return replayed_candidate
        raise
    return updated_candidate


def merge_candidate(
    settings: Settings,
    candidate_id: str,
    *,
    target_candidate_id: str,
    actor_role: ActorRole,
    actor_id: str | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    notes: str | None = None,
    merged_at: datetime | None = None,
) -> CandidateItem:
    if candidate_id == target_candidate_id:
        raise CandidateStateError("cannot merge a candidate into itself")

    current_candidate = get_candidate(settings, candidate_id)
    current_target = get_candidate(settings, target_candidate_id)
    _assert_review_actor_id(actor_id)
    _assert_review_authorized(
        current_candidate,
        actor_role=actor_role,
        action="candidate_merged",
    )
    if current_target.status not in {CandidateStatus.OPEN, CandidateStatus.PROMOTED}:
        raise CandidateStateError("target candidate must remain active to receive a merge")
    if current_candidate.kind is not current_target.kind:
        raise CandidateStateError("merge target must have the same candidate kind")
    if current_candidate.class_id != current_target.class_id:
        raise CandidateStateError("merge target must belong to the same class scope")
    if current_candidate.course_id != current_target.course_id:
        raise CandidateStateError("merge target must belong to the same course scope")

    transition_at = merged_at or datetime.now(UTC)
    updated_target = current_target.model_copy(
        update={
            "tags": _merge_unique_strings(current_target.tags, current_candidate.tags),
            "session_refs": _merge_unique_strings(
                current_target.session_refs, current_candidate.session_refs
            ),
            "source_refs": _merge_source_refs(
                current_target.source_refs,
                current_candidate.source_refs,
            ),
            "updated_at": transition_at,
        }
    )
    updated_candidate = current_candidate.model_copy(
        update={
            "status": CandidateStatus.MERGED,
            "merged_into": target_candidate_id,
            "approved_by": actor_id,
            "approved_at": transition_at,
            "updated_at": transition_at,
        }
    )
    mutation_request = _begin_transition_request(
        settings,
        entity_id=candidate_id,
        action="candidate_merged",
        actor_role=actor_role,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        request_fingerprint=_build_request_fingerprint(
            candidate_id=candidate_id,
            action="candidate_merged",
            actor_role=actor_role,
            actor_id=actor_id,
            target_candidate_id=target_candidate_id,
            target_identity=_build_merge_target_identity(current_target),
            requested_merged_at=_serialize_optional_timestamp(merged_at),
            notes=notes,
        ),
        created_at=transition_at,
    )
    replayed_candidate = _finalize_or_replay_merge(
        settings,
        mutation_request=mutation_request,
        current_candidate=current_candidate,
        current_target=current_target,
        expected_target=updated_target,
        target_candidate_id=target_candidate_id,
        actor_role=actor_role,
        actor_id=actor_id,
        request_id=request_id,
        idempotency_key=idempotency_key,
        notes=notes,
    )
    if replayed_candidate is not None:
        return replayed_candidate

    _assert_status(current_candidate, expected=CandidateStatus.OPEN)
    candidate_path = find_candidate_path(settings, candidate_id)
    target_candidate_path = find_candidate_path(settings, target_candidate_id)
    try:
        _apply_candidate_transaction(
            {
                target_candidate_path: updated_target,
                candidate_path: updated_candidate,
            },
            expected_current={
                target_candidate_path: current_target,
                candidate_path: current_candidate,
            },
            persist_audit=lambda: create_audit_event(
                settings,
                entity_type="candidate",
                entity_id=candidate_id,
                action="candidate_merged",
                actor_role=actor_role.value,
                actor_id=actor_id,
                from_status=current_candidate.status.value,
                to_status=updated_candidate.status.value,
                notes=notes,
                request_id=request_id,
                idempotency_key=idempotency_key,
                created_at=transition_at,
            ),
            mark_applied=lambda: _mark_transition_applied(
                settings,
                entity_id=candidate_id,
                action="candidate_merged",
                idempotency_key=idempotency_key,
                updated_at=transition_at,
            ),
        )
    except CandidateStateError as exc:
        replayed_candidate = _retry_changed_transition(
            exc,
            current_candidate_loader=lambda: (
                get_candidate(settings, candidate_id),
                get_candidate(settings, target_candidate_id),
            ),
            finalize=lambda latest: _finalize_or_replay_merge(
                settings,
                mutation_request=mutation_request,
                current_candidate=latest[0],
                current_target=latest[1],
                expected_target=updated_target,
                target_candidate_id=target_candidate_id,
                actor_role=actor_role,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                notes=notes,
            ),
        )
        if replayed_candidate is not None:
            return replayed_candidate
        raise
    return updated_candidate


def drop_candidate(
    settings: Settings,
    candidate_id: str,
    *,
    actor_role: ActorRole,
    actor_id: str | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    reason: DropReason | str | None = None,
    notes: str | None = None,
    dropped_at: datetime | None = None,
) -> CandidateItem:
    current_candidate = get_candidate(settings, candidate_id)
    _assert_review_actor_id(actor_id)
    _assert_review_authorized(
        current_candidate,
        actor_role=actor_role,
        action="candidate_dropped",
    )

    transition_at = dropped_at or datetime.now(UTC)
    normalized_reason = _normalize_drop_reason(reason)
    updated_candidate = current_candidate.model_copy(
        update={
            "status": CandidateStatus.DROPPED,
            "approved_by": actor_id,
            "approved_at": transition_at,
            "updated_at": transition_at,
        }
    )
    request_fingerprint_payload = {
        "candidate_id": candidate_id,
        "action": "candidate_dropped",
        "actor_role": actor_role,
        "actor_id": actor_id,
        "requested_dropped_at": _serialize_optional_timestamp(dropped_at),
        "notes": notes,
    }
    if normalized_reason is not None:
        request_fingerprint_payload["reason"] = normalized_reason.value

    mutation_request = _begin_transition_request(
        settings,
        entity_id=candidate_id,
        action="candidate_dropped",
        actor_role=actor_role,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        request_fingerprint=_build_request_fingerprint(**request_fingerprint_payload),
        created_at=transition_at,
    )
    replayed_candidate = _finalize_or_replay_drop(
        settings,
        mutation_request=mutation_request,
        current_candidate=current_candidate,
        actor_role=actor_role,
        actor_id=actor_id,
        request_id=request_id,
        idempotency_key=idempotency_key,
        reason=normalized_reason,
        notes=notes,
    )
    if replayed_candidate is not None:
        return replayed_candidate

    _assert_status(current_candidate, expected=CandidateStatus.OPEN)
    candidate_path = find_candidate_path(settings, candidate_id)
    try:
        _apply_candidate_transaction(
            {
                candidate_path: updated_candidate,
            },
            expected_current={
                candidate_path: current_candidate,
            },
            persist_audit=lambda: create_audit_event(
                settings,
                entity_type="candidate",
                entity_id=candidate_id,
                action="candidate_dropped",
                actor_role=actor_role.value,
                actor_id=actor_id,
                from_status=current_candidate.status.value,
                to_status=updated_candidate.status.value,
                notes=notes,
                details=_build_drop_audit_details(reason=normalized_reason),
                request_id=request_id,
                idempotency_key=idempotency_key,
                created_at=transition_at,
            ),
            mark_applied=lambda: _mark_transition_applied(
                settings,
                entity_id=candidate_id,
                action="candidate_dropped",
                idempotency_key=idempotency_key,
                updated_at=transition_at,
            ),
        )
    except CandidateStateError as exc:
        replayed_candidate = _retry_changed_transition(
            exc,
            current_candidate_loader=lambda: get_candidate(settings, candidate_id),
            finalize=lambda latest_candidate: _finalize_or_replay_drop(
                settings,
                mutation_request=mutation_request,
                current_candidate=latest_candidate,
                actor_role=actor_role,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                reason=normalized_reason,
                notes=notes,
            ),
        )
        if replayed_candidate is not None:
            return replayed_candidate
        raise
    return updated_candidate


def mark_candidate_wiki_synced(
    settings: Settings,
    candidate_id: str,
    *,
    synced_at: datetime | None = None,
) -> CandidateItem:
    current_candidate = get_candidate(settings, candidate_id)
    if current_candidate.status is not CandidateStatus.PROMOTED:
        raise CandidateStateError("only promoted candidates can be marked as wiki-synced")
    if (
        current_candidate.wiki_sync_status is WikiSyncStatus.SYNCED
        and current_candidate.wiki_synced_at is not None
    ):
        return current_candidate

    effective_synced_at = synced_at or datetime.now(UTC)
    updated_candidate = current_candidate.model_copy(
        update={
            "wiki_sync_status": WikiSyncStatus.SYNCED,
            "wiki_synced_at": effective_synced_at,
            "updated_at": effective_synced_at,
        }
    )
    candidate_path = find_candidate_path(settings, candidate_id)
    _apply_candidate_transaction(
        {candidate_path: updated_candidate},
        expected_current={candidate_path: current_candidate},
        persist_audit=lambda: None,
    )
    return updated_candidate


def refresh_candidate_wiki_sync_plan(
    settings: Settings,
    candidate_id: str,
    *,
    approval_plan_fingerprint: str,
    target_path: str | None = None,
    refreshed_at: datetime | None = None,
    current_candidate_snapshot: CandidateItem | None = None,
) -> CandidateItem:
    current_candidate = current_candidate_snapshot or get_candidate(settings, candidate_id)
    if current_candidate.status is not CandidateStatus.PROMOTED:
        raise CandidateStateError("only promoted candidates can refresh wiki sync plan")
    if current_candidate.wiki_sync_status is not WikiSyncStatus.PENDING:
        raise CandidateStateError("only pending wiki sync plans can be refreshed")
    if current_candidate.promotion_attempt_id is None:
        raise CandidateStateError("pending candidate is missing promotion_attempt_id")

    effective_refreshed_at = refreshed_at or datetime.now(UTC)
    updated_candidate = current_candidate.model_copy(
        update={
            "approval_plan_fingerprint": approval_plan_fingerprint,
            "wiki_sync_target_path": target_path or current_candidate.wiki_sync_target_path,
            "updated_at": effective_refreshed_at,
        }
    )
    candidate_path = find_candidate_path(settings, candidate_id)
    _apply_candidate_transaction(
        {candidate_path: updated_candidate},
        expected_current={candidate_path: current_candidate},
        persist_audit=lambda: None,
    )
    return updated_candidate


def build_candidate_path(settings: Settings, candidate: CandidateItem) -> Path:
    kind_directory = CANDIDATE_KIND_DIRECTORIES[candidate.kind]
    return (
        settings.data_root
        / "candidate"
        / kind_directory
        / candidate.class_id
        / f"{candidate.candidate_id}.json"
    )


def find_candidate_path(settings: Settings, candidate_id: str) -> Path:
    candidate_root = settings.data_root / "candidate"
    if not candidate_root.exists():
        raise CandidateNotFoundError(f"candidate store does not exist: {candidate_id}")

    matches = sorted(candidate_root.glob(f"**/{candidate_id}.json"))
    if not matches:
        raise CandidateNotFoundError(f"candidate not found: {candidate_id}")
    if len(matches) > 1:
        raise CandidateStateError(f"candidate id is ambiguous: {candidate_id}")
    return matches[0]


def _write_candidate(path: Path, candidate: CandidateItem) -> None:
    payload = candidate.model_dump(mode="json", exclude_none=True)
    _write_text_atomically(path, json.dumps(payload, indent=2) + "\n")


def _validate_candidate_payload(
    payload: dict[str, object],
) -> tuple[CandidateItem, bool]:
    had_updated_at = "updated_at" in payload
    normalized_payload = payload
    if not had_updated_at and "created_at" in payload:
        normalized_payload = {**payload, "updated_at": payload["created_at"]}
    return CandidateItem.model_validate(normalized_payload), had_updated_at


def _load_candidate_file(path: Path) -> CandidateItem:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidate, had_updated_at = _validate_candidate_payload(payload)
    if had_updated_at:
        return candidate

    try:
        lock_paths = _acquire_candidate_locks([path])
    except CandidateStateError:
        return candidate
    try:
        refreshed_payload = json.loads(path.read_text(encoding="utf-8"))
        candidate, refreshed_had_updated_at = _validate_candidate_payload(refreshed_payload)
        if not refreshed_had_updated_at:
            try:
                _write_candidate(path, candidate)
            except OSError:
                pass
    finally:
        _release_candidate_locks(lock_paths)
    return candidate


def _assert_status(candidate: CandidateItem, *, expected: CandidateStatus) -> None:
    if candidate.status is not expected:
        raise CandidateStateError(
            "candidate "
            f"{candidate.candidate_id} must be {expected.value}, "
            f"got {candidate.status.value}"
        )


def _assert_review_authorized(
    candidate: CandidateItem,
    *,
    actor_role: ActorRole,
    action: str,
) -> None:
    allowed_roles = _allowed_review_roles(candidate.kind, action=action)
    if actor_role not in allowed_roles:
        allowed_values = ", ".join(role.value for role in sorted(allowed_roles, key=str))
        raise CandidateStateError(
            f"{action} is not allowed for role {actor_role.value}; "
            f"expected one of: {allowed_values}"
        )


def _allowed_review_roles(kind: CandidateKind, *, action: str) -> set[ActorRole]:
    if kind is CandidateKind.OPERATIONS_NOTE:
        return {ActorRole.VALIDATOR}
    return {ActorRole.INSTRUCTOR, ActorRole.VALIDATOR}


def _assert_promotion_target(candidate: CandidateItem, *, target_page_id: str) -> None:
    expected_prefix = PROMOTION_PAGE_PREFIXES.get(candidate.kind)
    if expected_prefix is None:
        raise CandidateStateError(
            f"{candidate.kind.value} candidates cannot be promoted directly to the formal wiki"
        )
    if not target_page_id.startswith(expected_prefix):
        raise CandidateStateError(
            f"{candidate.kind.value} candidates must target {expected_prefix} pages"
        )


def _assert_approver_identity(*, approved_by: str, actor_id: str | None) -> None:
    if actor_id is None:
        raise CandidateStateError("actor_id is required for review actions")
    if approved_by != actor_id:
        raise CandidateStateError("approved_by must match actor_id for review actions")


def _assert_review_actor_id(actor_id: str | None) -> None:
    if actor_id is None:
        raise CandidateStateError("actor_id is required for review actions")


def _begin_create_candidate_request(
    settings: Settings,
    *,
    candidate: CandidateItem,
    actor_role: ActorRole,
    actor_id: str | None,
    idempotency_key: str | None,
):
    if idempotency_key is None:
        return None

    request_fingerprint = _build_candidate_create_request_fingerprint(
        candidate,
        actor_id=actor_id,
    )
    mutation_request = begin_mutation_request(
        settings,
        entity_type=CREATE_REQUEST_ENTITY_TYPE,
        entity_id=CREATE_REQUEST_ENTITY_ID,
        action=CREATE_ACTION,
        idempotency_key=idempotency_key,
        actor_role=actor_role.value,
        actor_id=actor_id,
        request_fingerprint=request_fingerprint,
        created_at=candidate.created_at,
    )
    if mutation_request.request_fingerprint != request_fingerprint:
        raise CandidateStateError("idempotency_key already exists for a different request")
    return mutation_request


def _ensure_create_candidate_request_intent(
    settings: Settings,
    *,
    mutation_request,
    candidate: CandidateItem,
    idempotency_key: str | None,
):
    if mutation_request is None or idempotency_key is None:
        return mutation_request

    expected_intent = _build_candidate_create_request_intent(settings, candidate)
    existing_intent = mutation_request.response_payload
    if existing_intent is not None:
        if existing_intent != expected_intent:
            if _create_request_has_durable_artifact(settings, mutation_request=mutation_request):
                raise CandidateStateError(
                    "stored created candidate does not match the idempotent request"
                )
        return mutation_request

    return store_mutation_request_response_payload(
        settings,
        entity_type=CREATE_REQUEST_ENTITY_TYPE,
        entity_id=CREATE_REQUEST_ENTITY_ID,
        action=CREATE_ACTION,
        idempotency_key=idempotency_key,
        updated_at=candidate.created_at,
        response_payload=expected_intent,
    )


def _create_request_has_durable_artifact(
    settings: Settings,
    *,
    mutation_request,
) -> bool:
    if list_audit_events(
        settings,
        entity_type="candidate",
        action=CREATE_ACTION,
        idempotency_key=mutation_request.idempotency_key,
    ):
        return True

    existing_intent = mutation_request.response_payload or {}
    expected_candidate_id = existing_intent.get("candidate_id")
    expected_path = existing_intent.get("path")
    if not isinstance(expected_candidate_id, str) or not isinstance(expected_path, str):
        return False

    try:
        stored_candidate_path = find_candidate_path(settings, expected_candidate_id)
    except CandidateNotFoundError:
        return False

    return str(stored_candidate_path.resolve()) == str(Path(expected_path).resolve())


def _apply_create_request_intent(
    candidate: CandidateItem,
    *,
    mutation_request,
) -> CandidateItem:
    if mutation_request is None or mutation_request.response_payload is None:
        return candidate

    request_intent = mutation_request.response_payload
    candidate_id = request_intent.get("candidate_id")
    if not isinstance(candidate_id, str):
        return candidate

    return candidate.model_copy(
        update={
            "candidate_id": candidate_id,
            "created_at": mutation_request.created_at,
            "updated_at": mutation_request.created_at,
        }
    )


def _begin_transition_request(
    settings: Settings,
    *,
    entity_id: str,
    action: str,
    actor_role: ActorRole,
    actor_id: str | None,
    idempotency_key: str | None,
    request_fingerprint: str,
    created_at: datetime,
):
    if idempotency_key is None:
        return None

    mutation_request = begin_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=entity_id,
        action=action,
        idempotency_key=idempotency_key,
        actor_role=actor_role.value,
        actor_id=actor_id,
        request_fingerprint=request_fingerprint,
        created_at=created_at,
    )
    if mutation_request.request_fingerprint != request_fingerprint:
        raise CandidateStateError("idempotency_key already exists for a different request")
    return mutation_request


def _mark_transition_applied(
    settings: Settings,
    *,
    entity_id: str,
    action: str,
    idempotency_key: str | None,
    updated_at: datetime,
) -> None:
    if idempotency_key is None:
        return

    mark_mutation_request_applied(
        settings,
        entity_type="candidate",
        entity_id=entity_id,
        action=action,
        idempotency_key=idempotency_key,
        updated_at=updated_at,
    )


def _build_request_fingerprint(**payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _build_candidate_create_request_fingerprint(
    candidate: CandidateItem,
    *,
    actor_id: str | None,
) -> str:
    candidate_payload = candidate.model_dump(
        mode="json",
        exclude={"candidate_id", "created_at", "updated_at"},
        exclude_none=True,
    )
    return _build_request_fingerprint(
        candidate=candidate_payload,
        actor_id=actor_id,
    )


def _build_candidate_create_request_intent(
    settings: Settings,
    candidate: CandidateItem,
) -> dict[str, object]:
    return {
        "candidate_id": candidate.candidate_id,
        "course_id": candidate.course_id,
        "class_id": candidate.class_id,
        "kind": candidate.kind.value,
        "path": str(build_candidate_path(settings, candidate)),
    }


def _candidate_state_fingerprint(
    candidate: CandidateItem,
    *,
    exclude: set[str] | None = None,
) -> str:
    return _build_request_fingerprint(
        candidate=candidate.model_dump(
            mode="json",
            exclude=exclude or set(),
            exclude_none=True,
        )
    )


def _serialize_optional_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _ensure_transition_audit(
    settings: Settings,
    *,
    entity_id: str,
    action: str,
    idempotency_key: str | None,
    persist_audit,
) -> None:
    if idempotency_key is None:
        return

    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=entity_id,
        action=action,
        idempotency_key=idempotency_key,
    )
    if not audit_events:
        persist_audit()


def _ensure_candidate_created_audit(
    settings: Settings,
    *,
    candidate: CandidateItem,
    actor_role: ActorRole | None = None,
    actor_id: str | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    notes: str | None = None,
) -> None:
    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action=CREATE_ACTION,
    )
    if audit_events:
        return

    create_audit_event(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action=CREATE_ACTION,
        actor_role=(actor_role or candidate.actor_role or ActorRole.SYSTEM).value,
        actor_id=actor_id,
        from_status=None,
        to_status=candidate.status.value,
        notes=notes or "Recovered missing candidate_created audit from existing candidate file.",
        request_id=request_id,
        idempotency_key=idempotency_key,
        created_at=candidate.created_at,
    )


def _finalize_or_replay_create_candidate(
    settings: Settings,
    *,
    mutation_request,
    idempotency_key: str | None,
) -> CandidateItem | None:
    if mutation_request is None or idempotency_key is None:
        return None

    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        action=CREATE_ACTION,
        idempotency_key=idempotency_key,
    )
    if not audit_events:
        if mutation_request.status == "applied":
            raise CandidateStateError(
                "stored created candidate does not match the idempotent request"
            )
        return None
    if len(audit_events) > 1:
        raise CandidateStateError("stored created candidate replay is ambiguous")

    try:
        candidate = get_candidate(settings, audit_events[0].entity_id)
    except CandidateNotFoundError as exc:
        raise CandidateStateError(
            "stored created candidate does not match the idempotent request"
        ) from exc
    expected_fingerprint = _build_candidate_create_request_fingerprint(
        candidate,
        actor_id=mutation_request.actor_id,
    )
    if expected_fingerprint != mutation_request.request_fingerprint:
        raise CandidateStateError("stored created candidate does not match the idempotent request")

    _mark_create_candidate_applied(
        settings,
        idempotency_key=idempotency_key,
        updated_at=datetime.now(UTC),
    )
    return candidate


def _mark_create_candidate_applied(
    settings: Settings,
    *,
    idempotency_key: str | None,
    updated_at: datetime,
) -> None:
    if idempotency_key is None:
        return

    mark_mutation_request_applied(
        settings,
        entity_type=CREATE_REQUEST_ENTITY_TYPE,
        entity_id=CREATE_REQUEST_ENTITY_ID,
        action=CREATE_ACTION,
        idempotency_key=idempotency_key,
        updated_at=updated_at,
    )


def _recover_create_candidate_without_audit(
    settings: Settings,
    *,
    mutation_request,
    requested_candidate: CandidateItem,
    actor_role: ActorRole,
    actor_id: str | None,
    request_id: str | None,
    idempotency_key: str | None,
    notes: str | None,
) -> CandidateItem | None:
    if mutation_request is None or idempotency_key is None:
        return None
    request_intent = mutation_request.response_payload
    if request_intent is None:
        return None
    expected_candidate_id = request_intent.get("candidate_id")
    expected_path = request_intent.get("path")
    if not isinstance(expected_candidate_id, str) or not isinstance(expected_path, str):
        return None

    try:
        stored_candidate_path = find_candidate_path(settings, expected_candidate_id)
    except CandidateNotFoundError:
        stored_candidate_path = None
    if stored_candidate_path is not None and str(stored_candidate_path.resolve()) != str(
        Path(expected_path).resolve()
    ):
        raise CandidateStateError("stored created candidate does not match the idempotent request")

    competing_requests = _list_competing_pending_create_requests(
        settings,
        mutation_request=mutation_request,
        idempotency_key=idempotency_key,
    )
    if competing_requests:
        return None

    matching_candidates = [
        candidate
        for candidate in list_candidates(settings, class_id=requested_candidate.class_id)
        if candidate.course_id == requested_candidate.course_id
        and candidate.candidate_id == expected_candidate_id
        and not list_audit_events(
            settings,
            entity_type="candidate",
            entity_id=candidate.candidate_id,
            action=CREATE_ACTION,
        )
        and _build_candidate_create_request_fingerprint(
            candidate,
            actor_id=mutation_request.actor_id,
        )
        == mutation_request.request_fingerprint
    ]
    if not matching_candidates:
        return None
    if len(matching_candidates) > 1:
        raise CandidateStateError("stored created candidate replay is ambiguous")

    recovered_candidate = matching_candidates[0]
    _ensure_candidate_created_audit(
        settings,
        candidate=recovered_candidate,
        actor_role=actor_role,
        actor_id=actor_id,
        request_id=request_id,
        idempotency_key=idempotency_key,
        notes=notes,
    )
    _mark_create_candidate_applied(
        settings,
        idempotency_key=idempotency_key,
        updated_at=datetime.now(UTC),
    )
    return recovered_candidate


def _list_competing_pending_create_requests(
    settings: Settings,
    *,
    mutation_request,
    idempotency_key: str | None,
) -> list:
    if mutation_request is None:
        return []

    return [
        request
        for request in list_mutation_requests(
            settings,
            entity_type=CREATE_REQUEST_ENTITY_TYPE,
            entity_id=CREATE_REQUEST_ENTITY_ID,
            action=CREATE_ACTION,
            request_fingerprint=mutation_request.request_fingerprint,
            status="pending",
        )
        if request.idempotency_key != idempotency_key
    ]


def _has_competing_pending_create_requests(
    settings: Settings,
    *,
    mutation_request,
    idempotency_key: str | None,
) -> bool:
    return bool(
        _list_competing_pending_create_requests(
            settings,
            mutation_request=mutation_request,
            idempotency_key=idempotency_key,
        )
    )


def _candidate_belongs_to_other_create_lineage(
    settings: Settings,
    *,
    candidate_id: str,
    idempotency_key: str,
) -> bool:
    create_audits = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate_id,
        action=CREATE_ACTION,
    )
    if not create_audits:
        return False
    return not any(audit.idempotency_key == idempotency_key for audit in create_audits)


def _finalize_or_replay_promote(
    settings: Settings,
    *,
    mutation_request,
    current_candidate: CandidateItem,
    expected_candidate: CandidateItem,
    actor_role: ActorRole,
    actor_id: str | None,
    request_id: str | None,
    idempotency_key: str | None,
    notes: str | None,
) -> CandidateItem | None:
    if mutation_request is None:
        return None

    if _candidate_matches_promote(
        current_candidate,
        expected_candidate=expected_candidate,
        replay_started_at=mutation_request.created_at,
    ):
        _ensure_transition_audit(
            settings,
            entity_id=current_candidate.candidate_id,
            action="candidate_promoted",
            idempotency_key=idempotency_key,
            persist_audit=lambda: create_audit_event(
                settings,
                entity_type="candidate",
                entity_id=current_candidate.candidate_id,
                action="candidate_promoted",
                actor_role=actor_role.value,
                actor_id=actor_id,
                from_status=CandidateStatus.OPEN.value,
                to_status=CandidateStatus.PROMOTED.value,
                notes=notes,
                request_id=request_id,
                idempotency_key=idempotency_key,
                created_at=mutation_request.created_at,
            ),
        )
        _mark_transition_applied(
            settings,
            entity_id=current_candidate.candidate_id,
            action="candidate_promoted",
            idempotency_key=idempotency_key,
            updated_at=datetime.now(UTC),
        )
        return current_candidate

    if mutation_request.status == "applied":
        raise CandidateStateError("stored promoted candidate does not match the idempotent request")

    return None


def _finalize_or_replay_merge(
    settings: Settings,
    *,
    mutation_request,
    current_candidate: CandidateItem,
    current_target: CandidateItem,
    expected_target: CandidateItem,
    target_candidate_id: str,
    actor_role: ActorRole,
    actor_id: str | None,
    request_id: str | None,
    idempotency_key: str | None,
    notes: str | None,
) -> CandidateItem | None:
    if mutation_request is None:
        return None

    if _merge_transition_applied(
        current_candidate=current_candidate,
        current_target=current_target,
        expected_target=expected_target,
        target_candidate_id=target_candidate_id,
        actor_id=actor_id,
        replay_started_at=mutation_request.created_at,
    ):
        _ensure_transition_audit(
            settings,
            entity_id=current_candidate.candidate_id,
            action="candidate_merged",
            idempotency_key=idempotency_key,
            persist_audit=lambda: create_audit_event(
                settings,
                entity_type="candidate",
                entity_id=current_candidate.candidate_id,
                action="candidate_merged",
                actor_role=actor_role.value,
                actor_id=actor_id,
                from_status=CandidateStatus.OPEN.value,
                to_status=CandidateStatus.MERGED.value,
                notes=notes,
                request_id=request_id,
                idempotency_key=idempotency_key,
                created_at=mutation_request.created_at,
            ),
        )
        _mark_transition_applied(
            settings,
            entity_id=current_candidate.candidate_id,
            action="candidate_merged",
            idempotency_key=idempotency_key,
            updated_at=datetime.now(UTC),
        )
        return current_candidate

    if mutation_request.status == "applied":
        raise CandidateStateError("stored merged candidate does not match the idempotent request")

    return None


def _finalize_or_replay_drop(
    settings: Settings,
    *,
    mutation_request,
    current_candidate: CandidateItem,
    actor_role: ActorRole,
    actor_id: str | None,
    request_id: str | None,
    idempotency_key: str | None,
    reason: DropReason | None,
    notes: str | None,
) -> CandidateItem | None:
    if mutation_request is None:
        return None

    if _candidate_matches_drop(
        current_candidate,
        actor_id=actor_id,
        replay_started_at=mutation_request.created_at,
    ):
        _ensure_transition_audit(
            settings,
            entity_id=current_candidate.candidate_id,
            action="candidate_dropped",
            idempotency_key=idempotency_key,
            persist_audit=lambda: create_audit_event(
                settings,
                entity_type="candidate",
                entity_id=current_candidate.candidate_id,
                action="candidate_dropped",
                actor_role=actor_role.value,
                actor_id=actor_id,
                from_status=CandidateStatus.OPEN.value,
                to_status=CandidateStatus.DROPPED.value,
                notes=notes,
                details=_build_drop_audit_details(reason=reason),
                request_id=request_id,
                idempotency_key=idempotency_key,
                created_at=mutation_request.created_at,
            ),
        )
        _mark_transition_applied(
            settings,
            entity_id=current_candidate.candidate_id,
            action="candidate_dropped",
            idempotency_key=idempotency_key,
            updated_at=datetime.now(UTC),
        )
        return current_candidate

    if mutation_request.status == "applied":
        raise CandidateStateError("stored dropped candidate does not match the idempotent request")

    return None


def _candidate_matches_promote(
    current_candidate: CandidateItem,
    *,
    expected_candidate: CandidateItem,
    replay_started_at: datetime,
) -> bool:
    return (
        current_candidate.status is CandidateStatus.PROMOTED
        and current_candidate.approved_by == expected_candidate.approved_by
        and current_candidate.approved_at is not None
        and current_candidate.approved_at == replay_started_at
        and current_candidate.related_page_id == expected_candidate.related_page_id
    )


def _candidate_matches_drop(
    current_candidate: CandidateItem,
    *,
    actor_id: str | None,
    replay_started_at: datetime,
) -> bool:
    return (
        actor_id is not None
        and current_candidate.status is CandidateStatus.DROPPED
        and current_candidate.approved_by == actor_id
        and current_candidate.approved_at is not None
        and current_candidate.approved_at == replay_started_at
    )


def _merge_transition_applied(
    *,
    current_candidate: CandidateItem,
    current_target: CandidateItem,
    expected_target: CandidateItem,
    target_candidate_id: str,
    actor_id: str | None,
    replay_started_at: datetime,
) -> bool:
    return (
        current_candidate.status is CandidateStatus.MERGED
        and current_candidate.merged_into == target_candidate_id
        and actor_id is not None
        and current_candidate.approved_by == actor_id
        and current_candidate.approved_at is not None
        and current_candidate.approved_at == replay_started_at
        and _merge_target_matches_replay_scope(
            current_target,
            expected_target,
        )
        and set(expected_target.tags).issubset(current_target.tags)
        and set(expected_target.session_refs).issubset(current_target.session_refs)
        and _source_refs_subset(
            expected_target.source_refs,
            current_target.source_refs,
        )
    )


def _source_refs_subset(expected: list[SourceRef], current: list[SourceRef]) -> bool:
    current_keys = {
        (source_ref.source_id, source_ref.source_type, source_ref.chunk_id)
        for source_ref in current
    }
    expected_keys = {
        (source_ref.source_id, source_ref.source_type, source_ref.chunk_id)
        for source_ref in expected
    }
    return expected_keys.issubset(current_keys)


def _build_drop_audit_details(*, reason: DropReason | None) -> dict[str, object] | None:
    if reason is None:
        return None
    return {"reason": reason.value}


def _normalize_drop_reason(reason: DropReason | str | None) -> DropReason | None:
    if reason is None:
        return None
    if isinstance(reason, DropReason):
        return reason
    try:
        return DropReason(reason)
    except ValueError as exc:
        raise CandidateStateError("invalid drop reason") from exc


def _merge_target_matches_replay_scope(
    current_target: CandidateItem,
    expected_target: CandidateItem,
) -> bool:
    status_matches = current_target.status is expected_target.status
    promoted_after_merge = (
        expected_target.status is CandidateStatus.OPEN
        and current_target.status is CandidateStatus.PROMOTED
    )
    return (
        current_target.candidate_id == expected_target.candidate_id
        and current_target.kind is expected_target.kind
        and current_target.class_id == expected_target.class_id
        and current_target.course_id == expected_target.course_id
        and current_target.title == expected_target.title
        and current_target.summary == expected_target.summary
        and current_target.related_page_id == expected_target.related_page_id
        and (status_matches or promoted_after_merge)
    )


def _build_merge_target_identity(candidate: CandidateItem) -> dict[str, object]:
    return {
        "candidate_id": candidate.candidate_id,
        "kind": candidate.kind.value,
        "course_id": candidate.course_id,
        "class_id": candidate.class_id,
        "title": candidate.title,
        "summary": candidate.summary,
        "related_page_id": candidate.related_page_id,
    }


def _find_existing_candidate(settings: Settings, candidate_id: str) -> CandidateItem | None:
    candidate_root = settings.data_root / "candidate"
    if not candidate_root.exists():
        return None

    matches = sorted(candidate_root.glob(f"**/{candidate_id}.json"))
    if not matches:
        return None
    if len(matches) > 1:
        raise CandidateStateError(f"candidate id is ambiguous: {candidate_id}")

    return _load_candidate_file(matches[0])


def _find_matching_open_candidate(
    settings: Settings,
    candidate: CandidateItem,
) -> CandidateItem | None:
    open_candidates = list_candidates(
        settings,
        kind=candidate.kind,
        status=CandidateStatus.OPEN,
        class_id=candidate.class_id,
    )
    for existing_candidate in open_candidates:
        if existing_candidate.course_id != candidate.course_id:
            continue
        if existing_candidate.title != candidate.title:
            continue
        if existing_candidate.related_page_id != candidate.related_page_id:
            continue
        return existing_candidate
    return None


def _retry_changed_transition(
    exc: CandidateStateError,
    *,
    current_candidate_loader,
    finalize,
):
    if str(exc) != "candidate changed during transition":
        raise exc

    latest_state = current_candidate_loader()
    return finalize(latest_state)


def _apply_candidate_transaction(
    changes: dict[Path, CandidateItem],
    *,
    expected_current: dict[Path, CandidateItem | None],
    persist_audit,
    mark_applied=None,
) -> None:
    lock_paths = _acquire_candidate_locks(changes.keys())
    try:
        snapshots = {
            path: path.read_text(encoding="utf-8") if path.exists() else None for path in changes
        }

        for path, expected_candidate in expected_current.items():
            snapshot = snapshots[path]
            if expected_candidate is None:
                if snapshot is not None:
                    raise CandidateStateError("candidate changed during transition")
                continue
            if snapshot is None:
                raise CandidateStateError("candidate changed during transition")
            current_candidate, _ = _validate_candidate_payload(json.loads(snapshot))
            if current_candidate != expected_candidate:
                raise CandidateStateError("candidate changed during transition")

        try:
            for path, candidate in changes.items():
                _write_candidate(path, candidate)
            persist_audit()
        except Exception:
            for path, previous_contents in snapshots.items():
                if previous_contents is None:
                    path.unlink(missing_ok=True)
                    continue
                _write_text_atomically(path, previous_contents)
            raise

        if mark_applied is not None:
            mark_applied()
    finally:
        _release_candidate_locks(lock_paths)


def _write_text_atomically(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".tmp-{uuid.uuid4().hex[:8]}"
    temp_path.write_text(contents, encoding="utf-8")
    temp_path.replace(path)


def _acquire_candidate_locks(paths) -> list[Path]:
    try:
        return acquire_file_locks(
            paths,
            stale_after=CANDIDATE_LOCK_STALE_AFTER,
        )
    except FileLockBusyError as exc:
        raise CandidateLockError("candidate storage is busy, retry later") from exc


def _release_candidate_locks(lock_paths: list[Path]) -> None:
    release_file_locks(lock_paths)


def _merge_unique_strings(base: list[str], extra: list[str]) -> list[str]:
    seen = set(base)
    merged = list(base)
    for item in extra:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


def _merge_source_refs(base: list[SourceRef], extra: list[SourceRef]) -> list[SourceRef]:
    merged = list(base)
    seen = {
        (source_ref.source_id, source_ref.source_type, source_ref.chunk_id) for source_ref in base
    }

    for source_ref in extra:
        key = (source_ref.source_id, source_ref.source_type, source_ref.chunk_id)
        if key not in seen:
            merged.append(source_ref)
            seen.add(key)

    return merged
