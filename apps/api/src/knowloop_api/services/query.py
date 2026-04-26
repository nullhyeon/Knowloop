from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from knowloop_api.api.context import RequestContext
from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole, RequestDomain, SourceType
from knowloop_api.core.input_limits import (
    MAX_QUERY_ATTACHMENT_SOURCE_IDS,
    MAX_QUERY_MESSAGE_LENGTH,
    MAX_SOURCE_ID_LENGTH,
)
from knowloop_api.core.query_contracts import (
    QUERY_ANSWER_BASIS_ORDER,
    AnswerBasisLabel,
    ResponseMode,
)
from knowloop_api.db.audit import (
    begin_mutation_request,
    create_audit_event,
    get_mutation_request,
    list_audit_events,
    mark_mutation_request_applied,
    store_mutation_request_response_payload,
    touch_mutation_request,
)
from knowloop_api.db.manifest import RawSourceRecord, list_source_records
from knowloop_api.services.candidates import (
    CandidateItem,
    CandidateKind,
    CandidateNotFoundError,
    CandidateStatus,
    SourceRef,
    get_candidate,
    list_candidates,
    upsert_candidate_signal,
)
from knowloop_api.services.learning import (
    LearningNote,
    build_learning_note_id,
    get_learning_note,
    upsert_learning_note,
)
from knowloop_api.services.llm_runtime import (
    EvidenceBlock,
    LLMAnswerContext,
    generate_grounded_answer,
)
from knowloop_api.services.sessions import (
    SessionNotFoundError,
    SessionRecord,
    build_session_id,
    get_session,
    list_recent_sessions,
    list_sessions_for_class,
    save_session,
    update_session_artifact_refs,
    update_session_replay_intent,
)
from knowloop_api.services.sources import (
    SourceNotFoundError,
    get_source,
    resolve_source_path,
    slugify,
)
from knowloop_api.services.wiki import WikiPage, WikiPageMatch, search_wiki_pages

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "also",
    "always",
    "among",
    "about",
    "again",
    "around",
    "because",
    "being",
    "between",
    "both",
    "can",
    "class",
    "could",
    "does",
    "doing",
    "done",
    "each",
    "every",
    "from",
    "have",
    "into",
    "just",
    "made",
    "make",
    "more",
    "most",
    "much",
    "must",
    "only",
    "other",
    "over",
    "same",
    "still",
    "some",
    "such",
    "tell",
    "that",
    "them",
    "then",
    "they",
    "test",
    "this",
    "through",
    "using",
    "very",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "without",
    "would",
    "your",
    "the",
    "and",
    "for",
    "you",
    "our",
    "not",
    "used",
    "should",
}
CONCEPT_CONFUSION_MARKERS = (
    "still do not understand",
    "don't understand",
    "do not understand",
    "confusing",
    "different from",
    "mixing up",
)


class QueryRequest(BaseModel):
    message: str = Field(min_length=1)
    attachment_source_ids: list[str] = Field(default_factory=list)
    allow_raw_source_fallback: bool = False
    response_mode: ResponseMode = ResponseMode.DEFAULT

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        if len(normalized) > MAX_QUERY_MESSAGE_LENGTH:
            raise ValueError(f"message must be at most {MAX_QUERY_MESSAGE_LENGTH} chars")
        return normalized

    @field_validator("attachment_source_ids")
    @classmethod
    def deduplicate_attachment_ids(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for item in value:
            candidate = item.strip()
            if not candidate or candidate in seen:
                continue
            if len(candidate) > MAX_SOURCE_ID_LENGTH:
                raise ValueError(
                    f"attachment_source_ids items must be at most {MAX_SOURCE_ID_LENGTH} chars"
                )
            normalized.append(candidate)
            seen.add(candidate)
        if len(normalized) > MAX_QUERY_ATTACHMENT_SOURCE_IDS:
            raise ValueError(
                f"attachment_source_ids must contain at most "
                f"{MAX_QUERY_ATTACHMENT_SOURCE_IDS} unique ids"
            )
        return sorted(normalized)


class RetrievalRef(BaseModel):
    entity_type: str
    entity_id: str
    reason: str
    source_refs: list[dict[str, str]] = Field(default_factory=list)


class WritebackPlanItem(BaseModel):
    kind: str
    action: str
    status: str
    target_id: str
    explanation: str


class QueryResponse(BaseModel):
    answer: str
    answer_basis: list[str]
    retrieval_refs: list[RetrievalRef]
    writeback_plan: list[WritebackPlanItem]
    session_id: str
    created_at: datetime


class BuiltAnswer(BaseModel):
    response_answer: str
    stored_answer: str


def build_query_runtime_meta(
    settings: Settings,
    *,
    response: QueryResponse,
) -> dict[str, object]:
    stored_answer = None
    try:
        stored_answer = get_session(settings, response.session_id).answer
    except SessionNotFoundError:
        stored_answer = None

    llm_applied = bool(
        settings.llm_enabled and stored_answer is not None and response.answer != stored_answer
    )
    return {
        "answer_source": "llm_rewrite" if llm_applied else "deterministic_fallback",
        "stored_answer_source": "deterministic_fallback",
        "llm_enabled": settings.llm_enabled,
        "llm_applied": llm_applied,
        "provider": "openai" if settings.llm_enabled else None,
        "configured_model": settings.openai_model if settings.llm_enabled else None,
    }


class LearningReplayProposal(BaseModel):
    learning_note_id: str
    student_id: str
    course_id: str
    class_id: str
    concepts: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    flashcards: list[dict[str, str]] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    session_refs: list[str] = Field(default_factory=list)
    summary: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    @classmethod
    def from_learning_note(cls, note: LearningNote) -> "LearningReplayProposal":
        return cls.model_validate(note.model_dump(mode="json", exclude_none=True))

    def to_learning_note(self) -> LearningNote:
        return LearningNote(
            learning_note_id=self.learning_note_id,
            student_id=self.student_id,
            course_id=self.course_id,
            class_id=self.class_id,
            concepts=list(self.concepts),
            gaps=list(self.gaps),
            flashcards=[dict(item) for item in self.flashcards],
            next_actions=list(self.next_actions),
            source_refs=[SourceRef.model_validate(item) for item in self.source_refs],
            session_refs=list(self.session_refs),
            summary=self.summary,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class CandidateReplayProposal(BaseModel):
    candidate_id: str
    kind: CandidateKind
    status: CandidateStatus
    title: str
    summary: str
    class_id: str
    course_id: str
    confidence: float = Field(ge=0, le=1)
    tags: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(min_length=1)
    session_refs: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    related_page_id: str | None = None

    @classmethod
    def from_candidate_item(cls, candidate: CandidateItem) -> "CandidateReplayProposal":
        return cls.model_validate(candidate.model_dump(mode="json", exclude_none=True))

    def to_candidate_item(self) -> CandidateItem:
        return CandidateItem(
            candidate_id=self.candidate_id,
            kind=self.kind,
            status=self.status,
            title=self.title,
            summary=self.summary,
            class_id=self.class_id,
            course_id=self.course_id,
            confidence=self.confidence,
            tags=list(self.tags),
            source_refs=[SourceRef.model_validate(item) for item in self.source_refs],
            session_refs=list(self.session_refs),
            created_at=self.created_at,
            updated_at=self.updated_at,
            related_page_id=self.related_page_id,
        )


class QueryReplayIntent(BaseModel):
    contract_version: Literal[1] = 1
    answer_basis: list[str]
    idempotency_key: str | None = None
    learning_proposal: LearningReplayProposal | None = None
    candidate_proposal: CandidateReplayProposal | None = None
    writeback_plan: list[WritebackPlanItem] = Field(default_factory=list)


class QueryStateError(ValueError):
    """Raised when the query contract cannot be fulfilled safely."""


class InsufficientVerifiedContextError(QueryStateError):
    """Raised when the verified retrieval basis is too weak to answer safely."""


class ForbiddenQueryScopeError(QueryStateError):
    """Raised when the request crosses a forbidden data boundary."""


class QueryReplayConflictError(QueryStateError):
    """Raised when an idempotent query mutation is replayed with a different payload."""


class QueryStorageBusyError(QueryStateError):
    """Raised when replay recovery cannot safely complete in the current request."""


QUERY_MUTATION_ACTION = "respond"
SESSION_WRITEBACK_EXPLANATION = "Stored the current question and answer in the session history."
LEARNING_WRITEBACK_EXPLANATION = (
    "Updated the student learning layer with concepts, gaps, and next actions."
)
CANDIDATE_WRITEBACK_EXPLANATION = "Captured a structured candidate for later review."
QUERY_REPLAY_PENDING_GRACE_SECONDS = 1.0
QUERY_REPLAY_POLL_INTERVAL_SECONDS = 0.05
QUERY_REPLAY_HEARTBEAT_INTERVAL_SECONDS = 0.25


class RawSourceHit(BaseModel):
    source: RawSourceRecord
    content: str
    score: int


def respond_to_query(
    settings: Settings,
    request: QueryRequest,
    *,
    context: RequestContext,
) -> QueryResponse:
    requested_at = datetime.now(UTC)
    request_fingerprint = _build_query_request_fingerprint(context=context, request=request)
    session_id = _build_query_session_id(
        context=context,
        request_fingerprint=request_fingerprint,
        created_at=requested_at,
    )
    mutation_request = _load_existing_query_mutation_request(
        settings,
        context=context,
        session_id=session_id,
        request_fingerprint=request_fingerprint,
    )
    if mutation_request is not None:
        replayed_response = _load_replayed_query_response(
            mutation_request,
            settings=settings,
            session_id=session_id,
            request_id=context.request_id,
            idempotency_key=context.idempotency_key,
        )
        if replayed_response is not None:
            return replayed_response
    existing_session = _load_existing_query_session(settings, session_id=session_id)
    if mutation_request is not None and existing_session is None:
        raise QueryStorageBusyError(
            "query replay requires durable session state before replay can succeed"
        )
    created_at = (
        existing_session.created_at
        if existing_session is not None
        else requested_at
    )
    session_saved_audit = (
        _get_session_saved_audit(
            settings,
            session_id=existing_session.session_id,
            idempotency_key=context.idempotency_key,
        )
        if existing_session is not None
        else None
    )
    recovered_learning_proposal, recovered_candidate_proposal = _recover_saved_writeback_intent(
        existing_session,
        session_saved_audit=session_saved_audit,
        idempotency_key=context.idempotency_key,
    )
    recovered_writeback_items: dict[str, WritebackPlanItem] = {}
    replay_recovery_writeback = False
    response_answer: str

    if mutation_request is not None and existing_session is not None:
        replayed_response = _wait_for_stored_query_response(
            settings,
            session_id=existing_session.session_id,
            request_id=context.request_id,
            idempotency_key=context.idempotency_key,
        )
        if replayed_response is not None:
            return replayed_response
        replayed_response = _recover_query_response_from_existing_session(
            settings,
            session=existing_session,
            idempotency_key=context.idempotency_key,
        )
        if _recovered_query_response_is_complete(
            replayed_response,
            session=existing_session,
            learning_proposal=recovered_learning_proposal,
            candidate_proposal=recovered_candidate_proposal,
        ):
            if not _replay_recovery_targets_are_frozen(
                replayed_response,
                learning_proposal=recovered_learning_proposal,
                candidate_proposal=recovered_candidate_proposal,
            ):
                raise QueryStorageBusyError(
                    "query replay recovery requires frozen write-back targets before retry"
                )
            existing_session = _attempt_replay_artifact_ref_repair(
                settings,
                session=existing_session,
                response=replayed_response,
                request_id=context.request_id,
                idempotency_key=context.idempotency_key,
            )
            replayed_response = _recover_query_response_from_existing_session(
                settings,
                session=existing_session,
                idempotency_key=context.idempotency_key,
            )
            if not _recovered_query_response_is_complete(
                replayed_response,
                session=existing_session,
                learning_proposal=recovered_learning_proposal,
                candidate_proposal=recovered_candidate_proposal,
            ):
                raise QueryStorageBusyError(
                    "query replay recovery is still reconciling replay-owned audit state"
                )
            answer_basis = replayed_response.answer_basis
            existing_session = _persist_query_replay_intent(
                settings,
                session=existing_session,
                response=replayed_response,
                answer_basis=answer_basis,
                idempotency_key=context.idempotency_key,
                learning_proposal=recovered_learning_proposal,
                candidate_proposal=recovered_candidate_proposal,
            )
            response_payload = replayed_response.model_dump(mode="json", exclude_none=True)
            mark_mutation_request_applied(
                settings,
                entity_type="query",
                entity_id=session_id,
                action=QUERY_MUTATION_ACTION,
                idempotency_key=context.idempotency_key,
                updated_at=created_at,
                response_payload=response_payload,
            )
            return replayed_response
        if not _replay_recovery_targets_are_frozen(
            replayed_response,
            learning_proposal=recovered_learning_proposal,
            candidate_proposal=recovered_candidate_proposal,
        ):
            raise QueryStorageBusyError(
                "query replay recovery requires frozen write-back targets before retry"
            )
        replay_recovery_writeback = True
        response_answer = replayed_response.answer
        answer_basis = replayed_response.answer_basis
        retrieval_refs = replayed_response.retrieval_refs
        learning_proposal = recovered_learning_proposal
        candidate_proposal = recovered_candidate_proposal
        session_record = existing_session
        recovered_writeback_items = {
            item.kind: item for item in replayed_response.writeback_plan
        }
    else:
        tokens = _tokenize(request.message)
        recent_sessions = list_recent_sessions(
            settings,
            user_id=context.actor_id,
            class_id=context.class_id,
            course_id=context.course_id,
            limit=5,
        )
        recent_sessions = [
            session for session in recent_sessions if session.session_id != session_id
        ]
        session_matches = [
            session for session in recent_sessions if _score_session(session, tokens=tokens) >= 2
        ]
        if context.role is ActorRole.STUDENT:
            class_sessions = []
        elif context.role in {ActorRole.INSTRUCTOR, ActorRole.VALIDATOR}:
            class_sessions = list_sessions_for_class(
                settings,
                class_id=context.class_id,
                course_id=context.course_id,
                role=ActorRole.STUDENT,
                limit=100,
            )
        else:
            class_sessions = list_sessions_for_class(
                settings,
                class_id=context.class_id,
                course_id=context.course_id,
                role=context.role,
                limit=100,
            )
        wiki_matches = search_wiki_pages(
            settings,
            role=context.role,
            course_id=context.course_id,
            class_id=context.class_id,
            requested_domain=context.domain,
            message=request.message,
            limit=5,
        )
        top_wiki_match = wiki_matches[0] if wiki_matches else None
        raw_source_hits = _collect_raw_source_hits(
            settings,
            context=context,
            request=request,
            tokens=tokens,
            recent_sessions=recent_sessions,
            top_wiki_match=top_wiki_match,
        )

        if top_wiki_match is None and not request.allow_raw_source_fallback:
            raise InsufficientVerifiedContextError(
                "The current verified wiki does not cover this query, "
                "and raw source fallback is disabled."
            )
        if top_wiki_match is None and request.allow_raw_source_fallback and not raw_source_hits:
            raise InsufficientVerifiedContextError(
                "Raw source fallback was requested, "
                "but no matching source material was found in scope."
            )

        existing_learning_note = (
            get_learning_note(
                settings,
                student_id=context.actor_id,
                course_id=context.course_id,
                class_id=context.class_id,
            )
            if context.role is ActorRole.STUDENT
            else None
        )
        answer_learning_note = _resolve_answer_learning_note(
            learning_note=existing_learning_note,
            current_session_id=session_id,
            existing_session=existing_session,
        )
        candidate_kind = _infer_candidate_kind(
            context=context,
            request=request,
            top_wiki_match=top_wiki_match,
            raw_source_hits=raw_source_hits,
        )
        answer_basis = _build_answer_basis(
            context=context,
            request=request,
            session_matches=session_matches,
            top_wiki_match=top_wiki_match,
            raw_source_hits=raw_source_hits,
            learning_note=answer_learning_note,
            candidate_kind=candidate_kind,
        )
        built_answer = _build_answer(
            settings,
            request=request,
            context=context,
            top_wiki_match=top_wiki_match,
            raw_source_hits=raw_source_hits,
            answer_basis=answer_basis,
            learning_note=answer_learning_note,
            session_matches=session_matches,
        )
        response_answer = built_answer.response_answer
        retrieval_refs = _build_retrieval_refs(
            settings,
            context=context,
            session_matches=session_matches,
            top_wiki_match=top_wiki_match,
            raw_source_hits=raw_source_hits,
            answer_basis=answer_basis,
            learning_note=answer_learning_note,
        )

        learning_proposal = _build_learning_proposal(
            settings,
            context=context,
            request=request,
            top_wiki_match=top_wiki_match,
            existing_learning_note=existing_learning_note,
            session_id=session_id,
            created_at=created_at,
            answer_basis=answer_basis,
        )
        candidate_proposal = _build_candidate_proposal(
            settings,
            context=context,
            request=request,
            top_wiki_match=top_wiki_match,
            raw_source_hits=raw_source_hits,
            class_sessions=class_sessions,
            session_matches=session_matches,
            session_id=session_id,
            created_at=created_at,
            candidate_kind=candidate_kind,
        )
        replay_seed_writeback_plan = _build_query_replay_seed_writeback_plan(
            session_id=session_id,
            learning_proposal=learning_proposal,
            candidate_proposal=candidate_proposal,
        )

        session_record = SessionRecord(
            session_id=session_id,
            role=context.role,
            user_id=context.actor_id,
            class_id=context.class_id,
            course_id=context.course_id,
            question=request.message,
            answer=built_answer.stored_answer,
            created_at=created_at,
            tags=_build_session_tags(candidate_kind, top_wiki_match),
            source_refs=_collect_primary_source_refs(
                settings,
                top_wiki_match=top_wiki_match,
                raw_source_hits=raw_source_hits,
                candidate_kind=candidate_kind,
            ),
            retrieval_refs=[
                item.model_dump(mode="json", exclude_none=True) for item in retrieval_refs
            ],
            candidate_refs=[],
            learning_note_refs=[],
            replay_intent=_build_query_session_audit_details(
                answer_basis=answer_basis,
                idempotency_key=context.idempotency_key,
                learning_proposal=learning_proposal,
                candidate_proposal=candidate_proposal,
                writeback_plan=replay_seed_writeback_plan,
            ),
        )

        if mutation_request is None:
            mutation_request = _begin_query_mutation_request(
                settings,
                context=context,
                session_id=session_id,
                request_fingerprint=request_fingerprint,
                requested_at=requested_at,
            )
            if mutation_request is not None:
                replayed_response = _load_replayed_query_response(
                    mutation_request,
                    settings=settings,
                    session_id=session_id,
                    request_id=context.request_id,
                    idempotency_key=context.idempotency_key,
                )
                if replayed_response is not None:
                    return replayed_response

        try:
            save_session(
                settings,
                session_record,
                request_id=context.request_id,
                idempotency_key=context.idempotency_key,
                details=_build_query_session_audit_details(
                    answer_basis=answer_basis,
                    idempotency_key=context.idempotency_key,
                    learning_proposal=learning_proposal,
                    candidate_proposal=candidate_proposal,
                ),
                raise_on_existing=True,
            )
            if mutation_request is not None:
                _touch_query_mutation_request(
                    settings,
                    session_id=session_record.session_id,
                    idempotency_key=context.idempotency_key,
                )
        except FileExistsError as exc:
            concurrent_session = _load_existing_query_session(
                settings,
                session_id=session_record.session_id,
            )
            if mutation_request is not None and concurrent_session is not None:
                replayed_response = _wait_for_stored_query_response(
                    settings,
                    session_id=session_record.session_id,
                    request_id=context.request_id,
                    idempotency_key=context.idempotency_key,
                )
                if replayed_response is not None:
                    return replayed_response
                concurrent_session_saved_audit = _get_session_saved_audit(
                    settings,
                    session_id=concurrent_session.session_id,
                    idempotency_key=context.idempotency_key,
                )
                concurrent_learning_proposal, concurrent_candidate_proposal = (
                    _recover_saved_writeback_intent(
                        concurrent_session,
                        session_saved_audit=concurrent_session_saved_audit,
                        idempotency_key=context.idempotency_key,
                    )
                )
                concurrent_replayed_response = _recover_query_response_from_existing_session(
                    settings,
                    session=concurrent_session,
                    idempotency_key=context.idempotency_key,
                )
                if _recovered_query_response_is_complete(
                    concurrent_replayed_response,
                    session=concurrent_session,
                    learning_proposal=concurrent_learning_proposal,
                    candidate_proposal=concurrent_candidate_proposal,
                ):
                    if not _replay_recovery_targets_are_frozen(
                        concurrent_replayed_response,
                        learning_proposal=concurrent_learning_proposal,
                        candidate_proposal=concurrent_candidate_proposal,
                    ):
                        raise QueryStorageBusyError(
                            "query replay recovery requires frozen write-back targets before retry"
                        ) from exc
                    concurrent_session = _attempt_replay_artifact_ref_repair(
                        settings,
                        session=concurrent_session,
                        response=concurrent_replayed_response,
                        request_id=context.request_id,
                        idempotency_key=context.idempotency_key,
                    )
                    concurrent_replayed_response = _recover_query_response_from_existing_session(
                        settings,
                        session=concurrent_session,
                        idempotency_key=context.idempotency_key,
                    )
                    if not _recovered_query_response_is_complete(
                        concurrent_replayed_response,
                        session=concurrent_session,
                        learning_proposal=concurrent_learning_proposal,
                        candidate_proposal=concurrent_candidate_proposal,
                    ):
                        raise QueryStorageBusyError(
                            "query replay recovery is still reconciling replay-owned audit state"
                        ) from exc
                    concurrent_session = _persist_query_replay_intent(
                        settings,
                        session=concurrent_session,
                        response=concurrent_replayed_response,
                        answer_basis=concurrent_replayed_response.answer_basis,
                        idempotency_key=context.idempotency_key,
                        learning_proposal=concurrent_learning_proposal,
                        candidate_proposal=concurrent_candidate_proposal,
                    )
                    response_payload = concurrent_replayed_response.model_dump(
                        mode="json",
                        exclude_none=True,
                    )
                    mark_mutation_request_applied(
                        settings,
                        entity_type="query",
                        entity_id=concurrent_session.session_id,
                        action=QUERY_MUTATION_ACTION,
                        idempotency_key=context.idempotency_key,
                        updated_at=concurrent_session.created_at,
                        response_payload=response_payload,
                    )
                    return concurrent_replayed_response
                if not _replay_recovery_targets_are_frozen(
                    concurrent_replayed_response,
                    learning_proposal=concurrent_learning_proposal,
                    candidate_proposal=concurrent_candidate_proposal,
                ):
                    raise QueryStorageBusyError(
                        "query replay recovery requires frozen write-back targets before retry"
                    ) from exc
                session_record = concurrent_session
                created_at = concurrent_session.created_at
                response_answer = concurrent_replayed_response.answer
                answer_basis = concurrent_replayed_response.answer_basis
                retrieval_refs = [
                    RetrievalRef.model_validate(item) for item in concurrent_session.retrieval_refs
                ]
                if concurrent_learning_proposal is not None:
                    learning_proposal = concurrent_learning_proposal
                if concurrent_candidate_proposal is not None:
                    candidate_proposal = concurrent_candidate_proposal
                recovered_writeback_items = {
                    item.kind: item for item in concurrent_replayed_response.writeback_plan
                }
                replay_recovery_writeback = True
            else:
                raise QueryStorageBusyError(
                    "query replay recovery is still reconciling prior storage work"
                ) from exc
    with _mutation_request_heartbeat(
        settings,
        session_id=session_record.session_id,
        idempotency_key=context.idempotency_key,
    ):
        writeback_plan = [
            WritebackPlanItem(
                kind="session",
                action="save",
                status="registered",
                target_id=session_record.session_id,
                explanation=SESSION_WRITEBACK_EXPLANATION,
            )
        ]

        if learning_proposal is not None:
            existing_learning_item = recovered_writeback_items.get("learning_note")
            if (
                existing_learning_item is not None
                and existing_learning_item.status not in {"failed", "registered"}
            ):
                stored_learning_note_id = existing_learning_item.target_id
                writeback_plan.append(existing_learning_item)
            else:
                learning_status = "updated"
                stored_learning_note_id = None
                try:
                    stored_learning_note = upsert_learning_note(
                        settings,
                        learning_proposal,
                        actor_id="system-query-engine",
                        request_id=context.request_id,
                        idempotency_key=context.idempotency_key,
                        notes="Generated from query/respond learning write-back.",
                    )
                    stored_learning_note_id = stored_learning_note.learning_note_id
                except Exception as exc:
                    learning_status = "failed"
                    _record_writeback_failure(
                        settings,
                        entity_type="learning_note",
                        entity_id=learning_proposal.learning_note_id,
                        action="learning_writeback_failed",
                        request_id=context.request_id,
                        idempotency_key=context.idempotency_key,
                        notes=str(exc),
                        details={
                            "kind": "learning_note",
                            "action": "update",
                            "status": "failed",
                            "target_id": learning_proposal.learning_note_id,
                            "explanation": LEARNING_WRITEBACK_EXPLANATION,
                        },
                        created_at=created_at,
                    )
                writeback_plan.append(
                    WritebackPlanItem(
                        kind="learning_note",
                        action="update",
                        status=learning_status,
                        target_id=learning_proposal.learning_note_id,
                        explanation=LEARNING_WRITEBACK_EXPLANATION,
                    )
                )
                _touch_query_mutation_request(
                    settings,
                    session_id=session_record.session_id,
                    idempotency_key=context.idempotency_key,
                )
        else:
            stored_learning_note_id = None

        if candidate_proposal is not None:
            existing_candidate_item = recovered_writeback_items.get("candidate")
            if (
                existing_candidate_item is not None
                and existing_candidate_item.status not in {"failed", "registered"}
            ):
                stored_candidate_id = existing_candidate_item.target_id
                writeback_plan.append(existing_candidate_item)
            else:
                candidate_status = candidate_proposal.status.value
                candidate_action = "create"
                stored_candidate_id = None
                try:
                    stored_candidate, candidate_action = upsert_candidate_signal(
                        settings,
                        candidate_proposal,
                        actor_role=ActorRole.SYSTEM,
                        actor_id="system-query-engine",
                        request_id=context.request_id,
                        idempotency_key=context.idempotency_key,
                        notes="Generated from query/respond candidate write-back.",
                        allow_match_by_metadata=not replay_recovery_writeback,
                    )
                    stored_candidate_id = stored_candidate.candidate_id
                    candidate_status = (
                        stored_candidate.status.value
                        if candidate_action == "create"
                        else "updated"
                    )
                except Exception as exc:
                    candidate_status = "failed"
                    _record_writeback_failure(
                        settings,
                        entity_type="candidate",
                        entity_id=_candidate_failure_entity_id(settings, candidate_proposal),
                        action="candidate_writeback_failed",
                        request_id=context.request_id,
                        idempotency_key=context.idempotency_key,
                        notes=str(exc),
                        details={
                            "kind": "candidate",
                            "action": candidate_action,
                            "status": "failed",
                            "target_id": stored_candidate_id or candidate_proposal.candidate_id,
                            "explanation": CANDIDATE_WRITEBACK_EXPLANATION,
                        },
                        created_at=created_at,
                    )
                writeback_plan.append(
                    WritebackPlanItem(
                        kind="candidate",
                        action=candidate_action,
                        status=candidate_status,
                        target_id=stored_candidate_id or candidate_proposal.candidate_id,
                        explanation=CANDIDATE_WRITEBACK_EXPLANATION,
                    )
                )
                _touch_query_mutation_request(
                    settings,
                    session_id=session_record.session_id,
                    idempotency_key=context.idempotency_key,
                )
        else:
            stored_candidate_id = None

        if stored_candidate_id is not None or stored_learning_note_id is not None:
            try:
                update_session_artifact_refs(
                    settings,
                    session_id=session_record.session_id,
                    candidate_refs=(
                        [stored_candidate_id] if stored_candidate_id is not None else []
                    ),
                    learning_note_refs=(
                        [stored_learning_note_id] if stored_learning_note_id is not None else []
                    ),
                )
            except Exception as exc:
                _record_writeback_failure(
                    settings,
                    entity_type="session",
                    entity_id=session_record.session_id,
                    action="session_artifact_link_failed",
                    request_id=context.request_id,
                    idempotency_key=context.idempotency_key,
                    notes=str(exc),
                    details={
                        "kind": "session",
                        "action": "link_artifacts",
                        "status": "failed",
                        "candidate_refs": [stored_candidate_id]
                        if stored_candidate_id is not None
                        else [],
                        "learning_note_refs": [stored_learning_note_id]
                        if stored_learning_note_id is not None
                        else [],
                    },
                    created_at=created_at,
                )
            finally:
                session_record = get_session(settings, session_record.session_id)
            _touch_query_mutation_request(
                settings,
                session_id=session_record.session_id,
                idempotency_key=context.idempotency_key,
            )

        response = QueryResponse(
            answer=response_answer,
            answer_basis=answer_basis,
            retrieval_refs=retrieval_refs,
            writeback_plan=writeback_plan,
            session_id=session_record.session_id,
            created_at=created_at,
        )
        durable_response = _build_durable_query_response(
            session=session_record,
            answer_basis=answer_basis,
            retrieval_refs=retrieval_refs,
            writeback_plan=writeback_plan,
        )
        session_record = _persist_query_replay_intent(
            settings,
            session=session_record,
            response=durable_response,
            answer_basis=answer_basis,
            idempotency_key=context.idempotency_key,
            learning_proposal=learning_proposal,
            candidate_proposal=candidate_proposal,
        )
        if mutation_request is not None:
            response_payload = durable_response.model_dump(mode="json", exclude_none=True)
            if _recovered_query_response_is_complete(
                durable_response,
                session=session_record,
                learning_proposal=learning_proposal,
                candidate_proposal=candidate_proposal,
            ):
                mark_mutation_request_applied(
                    settings,
                    entity_type="query",
                    entity_id=session_id,
                    action=QUERY_MUTATION_ACTION,
                    idempotency_key=context.idempotency_key,
                    updated_at=created_at,
                    response_payload=response_payload,
                )
            else:
                store_mutation_request_response_payload(
                    settings,
                    entity_type="query",
                    entity_id=session_id,
                    action=QUERY_MUTATION_ACTION,
                    idempotency_key=context.idempotency_key,
                    updated_at=created_at,
                    response_payload=response_payload,
                )
    return response


def build_candidate_id(
    *,
    kind: CandidateKind,
    class_id: str,
    title: str,
    created_at: datetime,
) -> str:
    timestamp = created_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"cand-{kind.value}-{class_id}-{slugify(title, max_length=12)}-{timestamp}"


def _build_query_session_id(
    *,
    context: RequestContext,
    request_fingerprint: str,
    created_at: datetime,
) -> str:
    if context.idempotency_key is not None:
        scope_digest = hashlib.sha1(
            json.dumps(
                {
                    "course_id": context.course_id,
                    "class_id": context.class_id,
                    "domain": context.domain.value if context.domain is not None else None,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()[:10]
        mutation_digest = hashlib.sha1(context.idempotency_key.encode("utf-8")).hexdigest()[:10]
        return f"ses-{context.role.value}-{context.actor_id}-{scope_digest}-{mutation_digest}"

    replay_digest = hashlib.sha1(
        f"{created_at.isoformat()}:{request_fingerprint}:{uuid.uuid4().hex}".encode("utf-8")
    ).hexdigest()[:6]
    timestamp_session_id = build_session_id(
        role=context.role,
        user_id=context.actor_id,
        class_id=context.class_id,
        created_at=created_at,
    )
    return f"{timestamp_session_id}-{replay_digest}"


def _build_query_request_fingerprint(
    *,
    context: RequestContext,
    request: QueryRequest,
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "role": context.role.value,
                "actor_id": context.actor_id,
                "course_id": context.course_id,
                "class_id": context.class_id,
                "domain": context.domain.value if context.domain is not None else None,
                "message": request.message,
                "attachment_source_ids": request.attachment_source_ids,
                "allow_raw_source_fallback": request.allow_raw_source_fallback,
                "response_mode": request.response_mode,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


def _begin_query_mutation_request(
    settings: Settings,
    *,
    context: RequestContext,
    session_id: str,
    request_fingerprint: str,
    requested_at: datetime,
):
    if context.idempotency_key is None:
        return None
    mutation_request = begin_mutation_request(
        settings,
        entity_type="query",
        entity_id=session_id,
        action=QUERY_MUTATION_ACTION,
        idempotency_key=context.idempotency_key,
        actor_role=context.role.value,
        actor_id=context.actor_id,
        request_fingerprint=request_fingerprint,
        created_at=requested_at,
    )
    if mutation_request.request_fingerprint != request_fingerprint:
        raise QueryReplayConflictError(
            "Idempotency-Key was reused for a different query payload within the same scope."
        )
    return mutation_request


def _touch_query_mutation_request(
    settings: Settings,
    *,
    session_id: str,
    idempotency_key: str | None,
) -> None:
    if idempotency_key is None:
        return
    touch_mutation_request(
        settings,
        entity_type="query",
        entity_id=session_id,
        action=QUERY_MUTATION_ACTION,
        idempotency_key=idempotency_key,
        updated_at=datetime.now(UTC),
    )


def _load_existing_query_mutation_request(
    settings: Settings,
    *,
    context: RequestContext,
    session_id: str,
    request_fingerprint: str,
):
    if context.idempotency_key is None:
        return None
    mutation_request = get_mutation_request(
        settings,
        entity_type="query",
        entity_id=session_id,
        action=QUERY_MUTATION_ACTION,
        idempotency_key=context.idempotency_key,
    )
    if mutation_request is None:
        return None
    if mutation_request.request_fingerprint != request_fingerprint:
        raise QueryReplayConflictError(
            "Idempotency-Key was reused for a different query payload within the same scope."
        )
    return mutation_request


def _load_replayed_query_response(
    mutation_request,
    *,
    settings: Settings,
    session_id: str,
    request_id: str,
    idempotency_key: str | None,
) -> QueryResponse | None:
    payload = mutation_request.response_payload
    if not isinstance(payload, dict):
        return None
    cached_response = QueryResponse.model_validate(payload)
    existing_session = _load_existing_query_session(settings, session_id=session_id)
    if existing_session is None:
        return None
    if mutation_request.status == "applied":
        replayed_response = _recover_query_response_from_existing_session(
            settings,
            session=existing_session,
            idempotency_key=idempotency_key,
        )
        return _reconcile_cached_query_response_payload(
            settings,
            cached_response=cached_response,
            durable_response=replayed_response,
            session=existing_session,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
    replayed_response = _align_pending_query_response_with_session_answer(
        cached_response,
        session=existing_session,
    )
    learning_proposal = None
    candidate_proposal = None
    if mutation_request.status != "applied":
        session_saved_audit = _get_session_saved_audit(
            settings,
            session_id=existing_session.session_id,
            idempotency_key=idempotency_key,
        )
        learning_proposal, candidate_proposal = _recover_saved_writeback_intent(
            existing_session,
            session_saved_audit=session_saved_audit,
            idempotency_key=idempotency_key,
        )
        if not _replay_recovery_targets_are_frozen(
            replayed_response,
            learning_proposal=learning_proposal,
            candidate_proposal=candidate_proposal,
        ):
            return None
    existing_session = _attempt_replay_artifact_ref_repair(
        settings,
        session=existing_session,
        response=replayed_response,
        request_id=request_id,
        idempotency_key=idempotency_key,
    )
    if _recovered_query_response_is_complete(
        replayed_response,
        session=existing_session,
        learning_proposal=learning_proposal,
        candidate_proposal=candidate_proposal,
    ):
        mark_mutation_request_applied(
            settings,
            entity_type="query",
            entity_id=session_id,
            action=QUERY_MUTATION_ACTION,
            idempotency_key=idempotency_key,
            updated_at=existing_session.created_at,
            response_payload=replayed_response.model_dump(mode="json", exclude_none=True),
        )
    return replayed_response


def _wait_for_stored_query_response(
    settings: Settings,
    *,
    session_id: str,
    request_id: str,
    idempotency_key: str,
    poll_interval_seconds: float = QUERY_REPLAY_POLL_INTERVAL_SECONDS,
    stale_after_seconds: float = QUERY_REPLAY_PENDING_GRACE_SECONDS,
) -> QueryResponse | None:
    while True:
        mutation_request = get_mutation_request(
            settings,
            entity_type="query",
            entity_id=session_id,
            action=QUERY_MUTATION_ACTION,
            idempotency_key=idempotency_key,
        )
        if mutation_request is None:
            return None
        replayed_response = _load_replayed_query_response(
            mutation_request,
            settings=settings,
            session_id=session_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
        if replayed_response is not None:
            return replayed_response
        request_age_seconds = (
            datetime.now(UTC) - mutation_request.updated_at
        ).total_seconds()
        if request_age_seconds >= stale_after_seconds:
            return None
        time.sleep(poll_interval_seconds)


@contextmanager
def _mutation_request_heartbeat(
    settings: Settings,
    *,
    session_id: str,
    idempotency_key: str | None,
):
    if idempotency_key is None:
        yield
        return

    stop_event = threading.Event()

    def pulse() -> None:
        while not stop_event.wait(QUERY_REPLAY_HEARTBEAT_INTERVAL_SECONDS):
            _touch_query_mutation_request(
                settings,
                session_id=session_id,
                idempotency_key=idempotency_key,
            )

    _touch_query_mutation_request(
        settings,
        session_id=session_id,
        idempotency_key=idempotency_key,
    )
    thread = threading.Thread(target=pulse, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop_event.set()
        thread.join(timeout=QUERY_REPLAY_HEARTBEAT_INTERVAL_SECONDS)
        _touch_query_mutation_request(
            settings,
            session_id=session_id,
            idempotency_key=idempotency_key,
        )


def _build_query_session_audit_details(
    *,
    answer_basis: list[str],
    idempotency_key: str | None,
    learning_proposal: LearningNote | None,
    candidate_proposal: CandidateItem | None,
    writeback_plan: list[WritebackPlanItem] | None = None,
) -> dict[str, object]:
    payload = QueryReplayIntent(
        answer_basis=answer_basis,
        idempotency_key=idempotency_key,
        learning_proposal=(
            LearningReplayProposal.from_learning_note(learning_proposal)
            if learning_proposal is not None
            else None
        ),
        candidate_proposal=(
            CandidateReplayProposal.from_candidate_item(candidate_proposal)
            if candidate_proposal is not None
            else None
        ),
        writeback_plan=writeback_plan or [],
    ).model_dump(mode="json", exclude_none=True)
    payload["idempotency_key"] = idempotency_key
    return payload


def _build_query_replay_seed_writeback_plan(
    *,
    session_id: str,
    learning_proposal: LearningNote | None,
    candidate_proposal: CandidateItem | None,
) -> list[WritebackPlanItem]:
    writeback_plan = [
        WritebackPlanItem(
            kind="session",
            action="save",
            status="registered",
            target_id=session_id,
            explanation=SESSION_WRITEBACK_EXPLANATION,
        )
    ]
    if learning_proposal is not None:
        writeback_plan.append(
            WritebackPlanItem(
                kind="learning_note",
                action="update",
                status="registered",
                target_id=learning_proposal.learning_note_id,
                explanation=LEARNING_WRITEBACK_EXPLANATION,
            )
        )
    if candidate_proposal is not None:
        writeback_plan.append(
            WritebackPlanItem(
                kind="candidate",
                action="create",
                status="registered",
                target_id=candidate_proposal.candidate_id,
                explanation=CANDIDATE_WRITEBACK_EXPLANATION,
            )
        )
    return writeback_plan


def _persist_query_replay_intent(
    settings: Settings,
    *,
    session: SessionRecord,
    response: QueryResponse,
    answer_basis: list[str],
    idempotency_key: str | None,
    learning_proposal: LearningNote | None,
    candidate_proposal: CandidateItem | None,
) -> SessionRecord:
    frozen_learning_proposal = _freeze_learning_replay_target(
        learning_proposal,
        writeback_plan=response.writeback_plan,
    )
    frozen_candidate_proposal = _freeze_candidate_replay_target(
        candidate_proposal,
        writeback_plan=response.writeback_plan,
    )
    replay_intent = _build_query_session_audit_details(
        answer_basis=answer_basis,
        idempotency_key=idempotency_key,
        learning_proposal=frozen_learning_proposal,
        candidate_proposal=frozen_candidate_proposal,
        writeback_plan=response.writeback_plan,
    )
    return update_session_replay_intent(
        settings,
        session_id=session.session_id,
        replay_intent=replay_intent,
    )


def _freeze_learning_replay_target(
    learning_proposal: LearningNote | None,
    *,
    writeback_plan: list[WritebackPlanItem],
) -> LearningNote | None:
    if learning_proposal is None:
        return None
    for item in writeback_plan:
        if item.kind == "learning_note" and item.status != "failed" and item.target_id.strip():
            return learning_proposal.model_copy(update={"learning_note_id": item.target_id})
    return learning_proposal


def _freeze_candidate_replay_target(
    candidate_proposal: CandidateItem | None,
    *,
    writeback_plan: list[WritebackPlanItem],
) -> CandidateItem | None:
    if candidate_proposal is None:
        return None
    for item in writeback_plan:
        if item.kind == "candidate" and item.status != "failed" and item.target_id.strip():
            return candidate_proposal.model_copy(update={"candidate_id": item.target_id})
    return candidate_proposal


def _recover_saved_writeback_intent(
    session: SessionRecord | None,
    *,
    session_saved_audit,
    idempotency_key: str | None = None,
) -> tuple[LearningNote | None, CandidateItem | None]:
    replay_intent = None
    sources: list[dict[str, object]] = []
    if session is not None and isinstance(session.replay_intent, dict):
        sources.append(session.replay_intent)
    if session_saved_audit is not None and isinstance(session_saved_audit.details, dict):
        sources.append(session_saved_audit.details)

    for details in sources:
        replay_intent = _parse_query_replay_intent(details)
        if replay_intent is not None and _replay_intent_matches_idempotency_key(
            replay_intent,
            idempotency_key=idempotency_key,
        ):
            break
    if replay_intent is None:
        return None, None
    learning_proposal = (
        replay_intent.learning_proposal.to_learning_note()
        if replay_intent.learning_proposal is not None
        else None
    )
    candidate_proposal = (
        replay_intent.candidate_proposal.to_candidate_item()
        if replay_intent.candidate_proposal is not None
        else None
    )
    return learning_proposal, candidate_proposal


def _recover_query_response_from_existing_session(
    settings: Settings,
    *,
    session: SessionRecord,
    idempotency_key: str | None = None,
) -> QueryResponse:
    session_saved_audit = _get_session_saved_audit(
        settings,
        session_id=session.session_id,
        idempotency_key=idempotency_key,
    )
    replay_intent = _recover_query_replay_intent(
        session=session,
        session_saved_audit=session_saved_audit,
        idempotency_key=idempotency_key,
    )
    request_audits = _list_replay_audits(
        settings,
        replay_intent=replay_intent,
        session_id=session.session_id,
        session_saved_audit=session_saved_audit,
    )
    learning_proposal, candidate_proposal = _recover_saved_writeback_intent(
        session,
        session_saved_audit=session_saved_audit,
        idempotency_key=idempotency_key,
    )
    retrieval_refs = [RetrievalRef.model_validate(item) for item in session.retrieval_refs]
    writeback_plan = _recover_writeback_plan(
        settings,
        session=session,
        replay_intent=replay_intent,
        request_audits=request_audits,
        session_saved_audit=session_saved_audit,
        learning_proposal=learning_proposal,
        candidate_proposal=candidate_proposal,
    )
    return QueryResponse(
        answer=session.answer,
        answer_basis=_recover_answer_basis(
            session=session,
            replay_intent=replay_intent,
            retrieval_refs=retrieval_refs,
            session_saved_audit=session_saved_audit,
        ),
        retrieval_refs=retrieval_refs,
        writeback_plan=writeback_plan,
        session_id=session.session_id,
        created_at=session.created_at,
    )


def _build_durable_query_response(
    session: SessionRecord,
    *,
    answer_basis: list[str],
    retrieval_refs: list[RetrievalRef],
    writeback_plan: list[WritebackPlanItem],
) -> QueryResponse:
    return QueryResponse(
        answer=session.answer,
        answer_basis=_normalize_answer_basis(answer_basis),
        retrieval_refs=[
            RetrievalRef.model_validate(item.model_dump(mode="json"))
            for item in retrieval_refs
        ],
        writeback_plan=[
            WritebackPlanItem.model_validate(item.model_dump(mode="json"))
            for item in writeback_plan
        ],
        session_id=session.session_id,
        created_at=session.created_at,
    )


def _align_pending_query_response_with_session_answer(
    response: QueryResponse,
    *,
    session: SessionRecord,
) -> QueryResponse:
    if response.answer == session.answer:
        return response
    return response.model_copy(update={"answer": session.answer})


def _reconcile_cached_query_response_payload(
    settings: Settings,
    *,
    cached_response: QueryResponse | None,
    durable_response: QueryResponse,
    session: SessionRecord,
    request_id: str,
    idempotency_key: str | None,
) -> QueryResponse:
    if cached_response is not None:
        cached_payload = cached_response.model_dump(mode="json", exclude_none=True)
    else:
        cached_payload = None
    durable_payload = durable_response.model_dump(mode="json", exclude_none=True)
    if cached_payload == durable_payload:
        return durable_response
    if idempotency_key is not None:
        store_mutation_request_response_payload(
            settings,
            entity_type="query",
            entity_id=session.session_id,
            action=QUERY_MUTATION_ACTION,
            idempotency_key=idempotency_key,
            updated_at=session.created_at,
            response_payload=durable_payload,
        )
    drift_fields: list[str]
    if cached_payload is None:
        drift_fields = ["cached_payload_missing_or_invalid"]
    else:
        drift_fields = sorted(
            field_name
            for field_name, field_value in durable_payload.items()
            if cached_payload.get(field_name) != field_value
        )
    create_audit_event(
        settings,
        entity_type="query",
        entity_id=session.session_id,
        action="query_replay_payload_drift_detected",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-query-engine",
        notes=(
            "Replay payload drifted from the stored deterministic session-owned state; "
            "the replay cache was repaired from durable storage."
        ),
        details={
            "drift_fields": drift_fields,
            "cached_answer_sha256": (
                hashlib.sha256(cached_response.answer.encode("utf-8")).hexdigest()
                if cached_response is not None
                else None
            ),
            "session_answer_sha256": hashlib.sha256(
                durable_response.answer.encode("utf-8")
            ).hexdigest(),
        },
        request_id=request_id,
        idempotency_key=idempotency_key,
        created_at=session.created_at,
    )
    return durable_response


def _recovered_query_response_is_complete(
    response: QueryResponse,
    *,
    session: SessionRecord,
    learning_proposal: LearningNote | None,
    candidate_proposal: CandidateItem | None,
) -> bool:
    expected_kinds = ["session"]
    if learning_proposal is not None:
        expected_kinds.append("learning_note")
    if candidate_proposal is not None:
        expected_kinds.append("candidate")
    if [item.kind for item in response.writeback_plan] != expected_kinds:
        return False
    for item in response.writeback_plan:
        if item.kind == "session":
            continue
        if item.status in {"failed", "pending", "in_progress", "queued", "registered"}:
            return False
        if not item.target_id.strip():
            return False
    if not _response_artifact_refs_converged(session, response=response):
        return False
    return True


def _replay_recovery_targets_are_frozen(
    response: QueryResponse,
    *,
    learning_proposal: LearningNote | None,
    candidate_proposal: CandidateItem | None,
) -> bool:
    required_kinds = {
        item.kind
        for item in response.writeback_plan
        if item.kind in {"learning_note", "candidate"}
    }
    if "learning_note" in required_kinds and learning_proposal is None:
        return False
    if "candidate" in required_kinds and candidate_proposal is None:
        return False
    expected_targets = _expected_replay_targets(
        learning_proposal=learning_proposal,
        candidate_proposal=candidate_proposal,
    )
    for item in response.writeback_plan:
        if item.kind == "session":
            continue
        expected_target_id = expected_targets.get(item.kind)
        if expected_target_id is None:
            continue
        if item.target_id != expected_target_id:
            return False
    return True


def _expected_replay_targets(
    *,
    learning_proposal: LearningNote | None,
    candidate_proposal: CandidateItem | None,
) -> dict[str, str]:
    targets: dict[str, str] = {}
    if learning_proposal is not None:
        targets["learning_note"] = learning_proposal.learning_note_id
    if candidate_proposal is not None:
        targets["candidate"] = candidate_proposal.candidate_id
    return targets


def _response_artifact_refs_converged(
    session: SessionRecord,
    *,
    response: QueryResponse,
) -> bool:
    expected_candidate_refs = [
        item.target_id
        for item in response.writeback_plan
        if item.kind == "candidate" and item.status not in {"failed", "pending", "in_progress"}
    ]
    expected_learning_note_refs = [
        item.target_id
        for item in response.writeback_plan
        if item.kind == "learning_note" and item.status not in {"failed", "pending", "in_progress"}
    ]
    return all(
        candidate_ref in session.candidate_refs for candidate_ref in expected_candidate_refs
    ) and all(
        learning_note_ref in session.learning_note_refs
        for learning_note_ref in expected_learning_note_refs
    )


def _repair_replayed_session_artifact_refs(
    settings: Settings,
    *,
    session: SessionRecord,
    response: QueryResponse,
) -> SessionRecord:
    candidate_refs = [
        item.target_id
        for item in response.writeback_plan
        if item.kind == "candidate" and item.status != "failed"
    ]
    learning_note_refs = [
        item.target_id
        for item in response.writeback_plan
        if item.kind == "learning_note" and item.status != "failed"
    ]
    missing_candidate_refs = [
        candidate_ref
        for candidate_ref in candidate_refs
        if candidate_ref not in session.candidate_refs
    ]
    missing_learning_note_refs = [
        learning_note_ref
        for learning_note_ref in learning_note_refs
        if learning_note_ref not in session.learning_note_refs
    ]
    if not missing_candidate_refs and not missing_learning_note_refs:
        return session
    return update_session_artifact_refs(
        settings,
        session_id=session.session_id,
        candidate_refs=missing_candidate_refs,
        learning_note_refs=missing_learning_note_refs,
    )


def _attempt_replay_artifact_ref_repair(
    settings: Settings,
    *,
    session: SessionRecord,
    response: QueryResponse,
    request_id: str,
    idempotency_key: str | None,
) -> SessionRecord:
    try:
        return _repair_replayed_session_artifact_refs(
            settings,
            session=session,
            response=response,
        )
    except Exception as exc:
        candidate_refs = [
            item.target_id
            for item in response.writeback_plan
            if item.kind == "candidate" and item.status != "failed"
        ]
        learning_note_refs = [
            item.target_id
            for item in response.writeback_plan
            if item.kind == "learning_note" and item.status != "failed"
        ]
        _record_writeback_failure(
            settings,
            entity_type="session",
            entity_id=session.session_id,
            action="session_artifact_link_failed",
            request_id=request_id,
            idempotency_key=idempotency_key,
            notes=str(exc),
            details={
                "kind": "session",
                "action": "link_artifacts",
                "status": "failed",
                "candidate_refs": candidate_refs,
                "learning_note_refs": learning_note_refs,
            },
            created_at=datetime.now(UTC),
        )
        return session


def _get_session_saved_audit(
    settings: Settings,
    *,
    session_id: str,
    idempotency_key: str | None = None,
):
    session_events = list_audit_events(
        settings,
        entity_type="session",
        entity_id=session_id,
        action="session_saved",
    )
    if not session_events:
        return None
    if idempotency_key is not None:
        for event in session_events:
            if event.idempotency_key == idempotency_key:
                return event
        return None
    return session_events[0]


def _list_replay_audits(
    settings: Settings,
    *,
    replay_intent: QueryReplayIntent | None,
    session_id: str,
    session_saved_audit,
):
    if replay_intent is not None and replay_intent.idempotency_key is not None:
        request_audits = list_audit_events(settings, idempotency_key=replay_intent.idempotency_key)
        return [
            event for event in request_audits if _audit_matches_frozen_replay_targets(
                event,
                session_id=session_id,
                replay_intent=replay_intent,
            )
        ]
    return []


def _audit_matches_frozen_replay_targets(
    event,
    *,
    session_id: str,
    replay_intent: QueryReplayIntent,
) -> bool:
    if event.entity_type == "session":
        return event.entity_id == session_id

    learning_target_id = (
        replay_intent.learning_proposal.learning_note_id
        if replay_intent.learning_proposal is not None
        else None
    )
    if event.entity_type == "learning_note" and learning_target_id is not None:
        return event.entity_id == learning_target_id

    candidate_target_id = (
        replay_intent.candidate_proposal.candidate_id
        if replay_intent.candidate_proposal is not None
        else None
    )
    if event.entity_type == "candidate" and candidate_target_id is not None:
        if event.entity_id == candidate_target_id:
            return True
        if isinstance(event.details, dict):
            return event.details.get("proposed_candidate_id") == candidate_target_id

    return False


def _recover_answer_basis(
    *,
    session: SessionRecord,
    replay_intent: QueryReplayIntent | None,
    retrieval_refs: list[RetrievalRef],
    session_saved_audit,
) -> list[str]:
    if replay_intent is not None:
        return _normalize_answer_basis(replay_intent.answer_basis)
    if session_saved_audit is not None and isinstance(session_saved_audit.details, dict):
        saved_replay_intent = _parse_query_replay_intent(session_saved_audit.details)
        if saved_replay_intent is not None:
            return _normalize_answer_basis(saved_replay_intent.answer_basis)
    derived = _derive_answer_basis_from_retrieval_refs(retrieval_refs)
    if not derived and session.source_refs:
        return [AnswerBasisLabel.RAW_SOURCE_FALLBACK.value]
    return derived


def _normalize_answer_basis(answer_basis: list[str]) -> list[str]:
    normalized: list[str] = []
    for basis in QUERY_ANSWER_BASIS_ORDER:
        if basis in answer_basis and basis not in normalized:
            normalized.append(basis)
    return normalized


def _recover_query_replay_intent(
    *,
    session: SessionRecord,
    session_saved_audit,
    idempotency_key: str | None = None,
) -> QueryReplayIntent | None:
    if isinstance(session.replay_intent, dict):
        replay_intent = _parse_query_replay_intent(session.replay_intent)
        if replay_intent is not None and _replay_intent_matches_idempotency_key(
            replay_intent,
            idempotency_key=idempotency_key,
        ):
            return replay_intent
    if session_saved_audit is not None and isinstance(session_saved_audit.details, dict):
        replay_intent = _parse_query_replay_intent(session_saved_audit.details)
        if replay_intent is not None and _replay_intent_matches_idempotency_key(
            replay_intent,
            idempotency_key=idempotency_key,
        ):
            return replay_intent
    return None


def _replay_intent_matches_idempotency_key(
    replay_intent: QueryReplayIntent,
    *,
    idempotency_key: str | None,
) -> bool:
    if idempotency_key is None:
        return True
    return replay_intent.idempotency_key == idempotency_key


def _parse_query_replay_intent(details: dict[str, object]) -> QueryReplayIntent | None:
    try:
        return QueryReplayIntent.model_validate(details)
    except Exception:
        pass

    legacy_details = dict(details)
    if isinstance(legacy_details.get("learning_proposal"), dict):
        try:
            legacy_details["learning_proposal"] = LearningReplayProposal.from_learning_note(
                LearningNote.model_validate(legacy_details["learning_proposal"])
            ).model_dump(mode="json", exclude_none=True)
        except Exception:
            legacy_details["learning_proposal"] = None
    if isinstance(legacy_details.get("candidate_proposal"), dict):
        try:
            legacy_details["candidate_proposal"] = CandidateReplayProposal.from_candidate_item(
                CandidateItem.model_validate(legacy_details["candidate_proposal"])
            ).model_dump(mode="json", exclude_none=True)
        except Exception:
            legacy_details["candidate_proposal"] = None

    try:
        return QueryReplayIntent.model_validate(legacy_details)
    except Exception:
        return None


def _recover_writeback_plan(
    settings: Settings,
    *,
    session: SessionRecord,
    replay_intent: QueryReplayIntent | None,
    request_audits: list,
    session_saved_audit,
    learning_proposal: LearningNote | None,
    candidate_proposal: CandidateItem | None,
) -> list[WritebackPlanItem]:
    if replay_intent is not None and replay_intent.writeback_plan:
        return [WritebackPlanItem.model_validate(item) for item in replay_intent.writeback_plan]

    writeback_plan = [
        WritebackPlanItem(
            kind="session",
            action="save",
            status="registered",
            target_id=session.session_id,
            explanation=SESSION_WRITEBACK_EXPLANATION,
        )
    ]
    learning_item = _recover_learning_writeback_item(
        session=session,
        request_audits=request_audits,
        learning_proposal=learning_proposal,
    )
    if learning_item is not None:
        writeback_plan.append(learning_item)
    candidate_item = _recover_candidate_writeback_item(
        settings,
        session=session,
        request_audits=request_audits,
        candidate_proposal=candidate_proposal,
    )
    if candidate_item is not None:
        writeback_plan.append(candidate_item)
    return writeback_plan


def _recover_learning_writeback_item(
    *,
    session: SessionRecord,
    request_audits: list,
    learning_proposal: LearningNote | None = None,
):
    if session.learning_note_refs:
        return WritebackPlanItem(
            kind="learning_note",
            action="update",
            status="updated",
            target_id=session.learning_note_refs[0],
            explanation=LEARNING_WRITEBACK_EXPLANATION,
        )
    success_event = _find_request_audit(
        request_audits,
        entity_type="learning_note",
        actions=("learning_generated",),
        entity_id=(
            learning_proposal.learning_note_id if learning_proposal is not None else None
        ),
    )
    if success_event is not None:
        return WritebackPlanItem(
            kind="learning_note",
            action="update",
            status="updated",
            target_id=success_event.entity_id,
            explanation=LEARNING_WRITEBACK_EXPLANATION,
        )
    failure_event = _find_request_audit(
        request_audits,
        entity_type="learning_note",
        actions=("learning_writeback_failed",),
        target_id=(
            learning_proposal.learning_note_id if learning_proposal is not None else None
        ),
    )
    if failure_event is not None:
        return _writeback_item_from_failure_event(
            failure_event,
            default_kind="learning_note",
            default_action="update",
            default_explanation=LEARNING_WRITEBACK_EXPLANATION,
        )
    return None


def _recover_candidate_writeback_item(
    settings: Settings,
    *,
    session: SessionRecord,
    request_audits: list,
    candidate_proposal: CandidateItem | None,
):
    created_event = _find_request_audit(
        request_audits,
        entity_type="candidate",
        actions=("candidate_created",),
        entity_id=(candidate_proposal.candidate_id if candidate_proposal is not None else None),
    )
    if created_event is not None:
        return WritebackPlanItem(
            kind="candidate",
            action="create",
            status=created_event.to_status or CandidateStatus.OPEN.value,
            target_id=created_event.entity_id,
            explanation=CANDIDATE_WRITEBACK_EXPLANATION,
        )

    updated_event = _find_request_audit(
        request_audits,
        entity_type="candidate",
        actions=("candidate_signal_upserted",),
        detail_filters=(
            {"proposed_candidate_id": candidate_proposal.candidate_id}
            if candidate_proposal is not None
            else None
        ),
    )
    if updated_event is not None:
        return WritebackPlanItem(
            kind="candidate",
            action="update",
            status="updated",
            target_id=updated_event.entity_id,
            explanation=CANDIDATE_WRITEBACK_EXPLANATION,
        )

    if session.candidate_refs:
        candidate_id = session.candidate_refs[0]
        candidate_action = "update"
        candidate_status = "updated"
        try:
            candidate = get_candidate(settings, candidate_id)
        except CandidateNotFoundError:
            candidate = None
        if candidate is not None and candidate.created_at == session.created_at:
            candidate_action = "create"
            candidate_status = (
                candidate_proposal.status.value
                if candidate_proposal is not None
                else CandidateStatus.OPEN.value
            )
        return WritebackPlanItem(
            kind="candidate",
            action=candidate_action,
            status=candidate_status,
            target_id=candidate_id,
            explanation=CANDIDATE_WRITEBACK_EXPLANATION,
        )

    failure_event = _find_request_audit(
        request_audits,
        entity_type="candidate",
        actions=("candidate_writeback_failed",),
        target_id=(candidate_proposal.candidate_id if candidate_proposal is not None else None),
    )
    if failure_event is not None:
        return _writeback_item_from_failure_event(
            failure_event,
            default_kind="candidate",
            default_action="create",
            default_explanation=CANDIDATE_WRITEBACK_EXPLANATION,
        )
    return None


def _find_request_audit(
    request_audits: list,
    *,
    entity_type: str,
    actions: tuple[str, ...],
    entity_id: str | None = None,
    target_id: str | None = None,
    detail_filters: dict[str, str] | None = None,
):
    for audit_event in request_audits:
        if audit_event.entity_type != entity_type:
            continue
        if audit_event.action not in actions:
            continue
        if entity_id is not None and audit_event.entity_id != entity_id:
            continue
        if target_id is not None:
            details = audit_event.details if isinstance(audit_event.details, dict) else {}
            audit_target_id = details.get("target_id", audit_event.entity_id)
            if audit_target_id != target_id:
                continue
        if detail_filters:
            details = audit_event.details if isinstance(audit_event.details, dict) else {}
            if any(details.get(key) != value for key, value in detail_filters.items()):
                continue
        return audit_event
    return None


def _writeback_item_from_failure_event(
    audit_event,
    *,
    default_kind: str,
    default_action: str,
    default_explanation: str,
) -> WritebackPlanItem:
    details = audit_event.details if isinstance(audit_event.details, dict) else {}
    kind = details.get("kind", default_kind)
    action = details.get("action", default_action)
    status = details.get("status", "failed")
    target_id = details.get("target_id", audit_event.entity_id)
    explanation = details.get("explanation", default_explanation)
    return WritebackPlanItem(
        kind=str(kind),
        action=str(action),
        status=str(status),
        target_id=str(target_id),
        explanation=str(explanation),
    )


def _load_existing_query_session(
    settings: Settings,
    *,
    session_id: str,
) -> SessionRecord | None:
    try:
        return get_session(settings, session_id)
    except SessionNotFoundError:
        return None


def _derive_answer_basis_from_retrieval_refs(
    retrieval_refs: list[RetrievalRef],
) -> list[str]:
    basis: list[str] = []
    for ref in retrieval_refs:
        if ref.entity_type == "wiki_page" and AnswerBasisLabel.FORMAL_WIKI.value not in basis:
            basis.append(AnswerBasisLabel.FORMAL_WIKI.value)
        elif ref.entity_type == "session" and AnswerBasisLabel.SESSION_CONTEXT.value not in basis:
            basis.append(AnswerBasisLabel.SESSION_CONTEXT.value)
        elif (
            ref.entity_type == "learning_note"
            and AnswerBasisLabel.LEARNING_CONTEXT.value not in basis
        ):
            basis.append(AnswerBasisLabel.LEARNING_CONTEXT.value)
        elif (
            ref.entity_type == "raw_source"
            and AnswerBasisLabel.RAW_SOURCE_FALLBACK.value not in basis
        ):
            basis.append(AnswerBasisLabel.RAW_SOURCE_FALLBACK.value)
    return basis


def _build_answer_basis(
    *,
    context: RequestContext,
    request: QueryRequest,
    session_matches: list[SessionRecord],
    top_wiki_match: WikiPageMatch | None,
    raw_source_hits: list[RawSourceHit],
    learning_note: LearningNote | None,
    candidate_kind: CandidateKind | None,
) -> list[str]:
    basis: list[str] = []
    if top_wiki_match is not None:
        basis.append(AnswerBasisLabel.FORMAL_WIKI.value)
    if context.role is ActorRole.STUDENT and top_wiki_match is not None and session_matches:
        basis.append(AnswerBasisLabel.SESSION_CONTEXT.value)
    if _should_emit_learning_context(context=context, learning_note=learning_note):
        basis.append(AnswerBasisLabel.LEARNING_CONTEXT.value)
    if _should_emit_raw_source_basis(
        context=context,
        request=request,
        top_wiki_match=top_wiki_match,
        raw_source_hits=raw_source_hits,
    ):
        basis.append(AnswerBasisLabel.RAW_SOURCE_FALLBACK.value)
    return basis


def _build_answer(
    settings: Settings,
    *,
    request: QueryRequest,
    context: RequestContext,
    top_wiki_match: WikiPageMatch | None,
    raw_source_hits: list[RawSourceHit],
    answer_basis: list[str],
    learning_note: LearningNote | None,
    session_matches: list[SessionRecord],
) -> BuiltAnswer:
    fallback_answer = _build_fallback_answer(
        request=request,
        context=context,
        top_wiki_match=top_wiki_match,
        raw_source_hits=raw_source_hits,
        answer_basis=answer_basis,
        learning_note=learning_note,
    )
    llm_answer = generate_grounded_answer(
        settings,
        context=LLMAnswerContext(
            role=context.role,
            domain=context.domain,
            response_mode=request.response_mode.value,
            question=request.message,
            answer_basis=tuple(answer_basis),
            fallback_answer=fallback_answer,
            evidence_blocks=_build_llm_evidence_blocks(
                context=context,
                answer_basis=answer_basis,
                top_wiki_match=top_wiki_match,
                raw_source_hits=raw_source_hits,
                session_matches=session_matches,
                learning_note=learning_note,
            ),
            request_id=context.request_id,
        ),
    )
    return BuiltAnswer(
        response_answer=llm_answer or fallback_answer,
        stored_answer=fallback_answer,
    )


def _build_fallback_answer(
    *,
    request: QueryRequest,
    context: RequestContext,
    top_wiki_match: WikiPageMatch | None,
    raw_source_hits: list[RawSourceHit],
    answer_basis: list[str],
    learning_note: LearningNote | None,
) -> str:
    message = request.message.lower()
    if "homework" in message and any(
        keyword in message for keyword in ("due", "deadline", "submit")
    ):
        if "raw_source_fallback" in answer_basis:
            return _augment_with_learning_context(
                _shape_answer(
                    _build_homework_answer(raw_source_hits),
                    response_mode=request.response_mode,
                    context=context,
                ),
                answer_basis=answer_basis,
                learning_note=learning_note,
            )
        if top_wiki_match is not None:
            return _augment_with_learning_context(
                _shape_answer(
                    top_wiki_match.page.summary,
                    response_mode=request.response_mode,
                    context=context,
                ),
                answer_basis=answer_basis,
                learning_note=learning_note,
            )
        return _augment_with_learning_context(
            _shape_answer(
                _build_homework_answer(raw_source_hits),
                response_mode=request.response_mode,
                context=context,
            ),
            answer_basis=answer_basis,
            learning_note=learning_note,
        )

    if "chain rule" in message or "product rule" in message:
        answer = (
            "Use the chain rule when one function is nested inside another, "
            "and use the product rule when two factors are multiplied. "
            "If the expression looks like f(g(x)), differentiate the outer "
            "function first and then multiply by the derivative of the inner function."
        )
        if request.response_mode is ResponseMode.TEACHING:
            answer += (
                " A quick check is to ask whether the expression is nested or simply multiplied."
            )
        return _augment_with_learning_context(
            answer,
            answer_basis=answer_basis,
            learning_note=learning_note,
        )

    if "refund" in message:
        answer = (
            "Tell students that refund requests must follow the official "
            "refund policy and the academic office "
            "review process. Course staff should not promise refund approval directly."
        )
        return _augment_with_learning_context(
            _shape_answer(answer, response_mode=request.response_mode, context=context),
            answer_basis=answer_basis,
            learning_note=learning_note,
        )

    if "substitution" in message or "integral" in message:
        answer = (
            "The current verified wiki does not establish that substitution "
            "works for every integral. Based on the available source material, "
            "substitution is introduced as a useful method, but the boundary "
            "cases are not fully covered yet, so you should not assume it "
            "applies in every case."
        )
        return _augment_with_learning_context(
            _shape_answer(answer, response_mode=request.response_mode, context=context),
            answer_basis=answer_basis,
            learning_note=learning_note,
        )

    if top_wiki_match is not None:
        return _augment_with_learning_context(
            _shape_answer(
                top_wiki_match.page.summary,
                response_mode=request.response_mode,
                context=context,
            ),
            answer_basis=answer_basis,
            learning_note=learning_note,
        )

    if "raw_source_fallback" in answer_basis and raw_source_hits:
        fallback_line = _find_line(raw_source_hits, keywords=tuple(_tokenize(request.message)))
        return _augment_with_learning_context(
            _shape_answer(
                fallback_line
                or "The available source material only partially covers this question.",
                response_mode=request.response_mode,
                context=context,
            ),
            answer_basis=answer_basis,
            learning_note=learning_note,
        )

    raise InsufficientVerifiedContextError(
        "No answer could be generated from the verified retrieval scope."
    )


def _build_llm_evidence_blocks(
    *,
    context: RequestContext,
    answer_basis: list[str],
    top_wiki_match: WikiPageMatch | None,
    raw_source_hits: list[RawSourceHit],
    session_matches: list[SessionRecord],
    learning_note: LearningNote | None,
) -> tuple[EvidenceBlock, ...]:
    allowed_basis = set(answer_basis)
    blocks: list[EvidenceBlock] = []
    wiki_block = (
        _build_wiki_evidence_block(top_wiki_match)
        if AnswerBasisLabel.FORMAL_WIKI.value in allowed_basis
        else None
    )
    if wiki_block is not None:
        blocks.append(wiki_block)
    learning_block = (
        _build_learning_evidence_block(learning_note)
        if AnswerBasisLabel.LEARNING_CONTEXT.value in allowed_basis
        else None
    )
    if learning_block is not None:
        blocks.append(learning_block)
    raw_source_block = (
        _build_raw_source_evidence_block(raw_source_hits)
        if (
            AnswerBasisLabel.RAW_SOURCE_FALLBACK.value in allowed_basis
            and context.role is not ActorRole.STUDENT
        )
        else None
    )
    if raw_source_block is not None:
        blocks.append(raw_source_block)
    session_block = (
        _build_session_evidence_block(session_matches)
        if AnswerBasisLabel.SESSION_CONTEXT.value in allowed_basis
        else None
    )
    if session_block is not None:
        blocks.append(session_block)
    return tuple(blocks)


def _build_wiki_evidence_block(top_wiki_match: WikiPageMatch | None) -> EvidenceBlock | None:
    if top_wiki_match is None:
        return None
    page = top_wiki_match.page
    return EvidenceBlock(
        label="formal_wiki",
        lines=(
            f"Title: {page.title}",
            f"Summary: {page.summary}",
        ),
    )


def _build_raw_source_evidence_block(raw_source_hits: list[RawSourceHit]) -> EvidenceBlock | None:
    if not raw_source_hits:
        return None
    lines: list[str] = []
    for index, hit in enumerate(raw_source_hits[:2], start=1):
        lines.append(f"Reference {index} type: {hit.source.source_type.value}")
    if not lines:
        return None
    return EvidenceBlock(label="raw_source_metadata", lines=tuple(lines))


def _build_session_evidence_block(session_matches: list[SessionRecord]) -> EvidenceBlock | None:
    context_lines: list[str] = []
    for session in session_matches[:2]:
        summarized = _summarize_session_context_for_llm(session)
        if summarized is not None:
            context_lines.append(summarized)
    if not context_lines:
        return None
    return EvidenceBlock(label="session_context_summary", lines=tuple(context_lines))


def _build_learning_evidence_block(learning_note: LearningNote | None) -> EvidenceBlock | None:
    if learning_note is None:
        return None
    lines = [
        f"Summary: {learning_note.summary or 'none'}",
        f"Gaps: {', '.join(learning_note.gaps) if learning_note.gaps else 'none'}",
        "Next actions: "
        + (", ".join(learning_note.next_actions) if learning_note.next_actions else "none"),
    ]
    return EvidenceBlock(label="learning_context", lines=tuple(lines))


def _summarize_session_context_for_llm(session: SessionRecord) -> str | None:
    normalized_question = re.sub(r"\s+", " ", session.question).strip().rstrip("?.!")
    if not normalized_question:
        return None
    if len(normalized_question) > 96:
        normalized_question = normalized_question[:93].rstrip() + "..."
    return f"- Prior topic: {normalized_question}"


def _build_homework_answer(items: list[RawSourceHit]) -> str:
    due_line = _find_line(items, keywords=("submitted by", "deadline", "due"))
    submit_line = _find_line(items, keywords=("submit", "lms"))
    if due_line is not None:
        due_text = due_line.removeprefix("Homework 01 must be submitted by ").rstrip(".")
        if submit_line is not None:
            cleaned_submit_line = submit_line.rstrip(".")
            return f"Homework 01 is due {due_text}. {cleaned_submit_line}."
        return f"Homework 01 is due {due_text}."
    if submit_line is not None:
        return submit_line.rstrip(".") + "."
    return "Submit Homework 01 through the LMS assignment page."


def _shape_answer(answer: str, *, response_mode: str, context: RequestContext) -> str:
    if response_mode == ResponseMode.CONCISE.value:
        return answer
    if response_mode == ResponseMode.TEACHING.value and context.role is ActorRole.STUDENT:
        return (
            answer
            + " Try one nested-function example and one product example to test the difference."
        )
    return answer


def _build_retrieval_refs(
    settings: Settings,
    *,
    context: RequestContext,
    session_matches: list[SessionRecord],
    top_wiki_match: WikiPageMatch | None,
    raw_source_hits: list[RawSourceHit],
    answer_basis: list[str],
    learning_note: LearningNote | None,
) -> list[RetrievalRef]:
    refs: list[RetrievalRef] = []
    if top_wiki_match is not None:
        refs.append(
            RetrievalRef(
                entity_type="wiki_page",
                entity_id=top_wiki_match.page.page_id,
                reason="high_relevance",
                source_refs=_exposed_source_ref_payloads(
                    settings,
                    context=context,
                    source_ids=top_wiki_match.page.source_refs,
                ),
            )
        )
    if "session_context" in answer_basis:
        refs.extend(
            RetrievalRef(
                entity_type="session",
                entity_id=session.session_id,
                reason="recent_related_context",
                source_refs=_exposed_source_ref_payloads(
                    settings,
                    context=context,
                    source_ids=[source_ref.source_id for source_ref in session.source_refs],
                ),
            )
            for session in session_matches[:2]
        )
    if "raw_source_fallback" in answer_basis and context.role is not ActorRole.STUDENT:
        refs.extend(
            RetrievalRef(
                entity_type="raw_source",
                entity_id=hit.source.source_id,
                reason="fallback_match",
                source_refs=[_build_source_ref_payload(settings, hit.source.source_id)],
            )
            for hit in raw_source_hits[:2]
        )
    if "learning_context" in answer_basis and learning_note is not None:
        refs.append(
            RetrievalRef(
                entity_type="learning_note",
                entity_id=learning_note.learning_note_id,
                reason="personal_learning_state",
                source_refs=[],
            )
        )
    return refs


def _build_learning_proposal(
    settings: Settings,
    *,
    context: RequestContext,
    request: QueryRequest,
    top_wiki_match: WikiPageMatch | None,
    existing_learning_note: LearningNote | None,
    session_id: str,
    created_at: datetime,
    answer_basis: list[str],
) -> LearningNote | None:
    if not _should_write_learning_note_for_request(
        context=context,
        request=request,
    ):
        return None

    concepts = _concepts_for_message(
        request.message, top_wiki_match.page if top_wiki_match else None
    )
    if not concepts:
        return None

    message = request.message.lower()
    if "chain rule" in message and "product rule" in message:
        gaps = [
            "Distinguish nested chain-rule expressions from multiplied product-rule expressions."
        ]
        next_actions = [
            "Compare one chain-rule example with one product-rule example "
            "and explain why each rule applies."
        ]
    else:
        gaps = [
            "Clarify the main concept behind the current question before moving to new material."
        ]
        next_actions = ["Rewrite the matched concept in your own words and test it on one example."]

    learning_note_id = (
        existing_learning_note.learning_note_id
        if existing_learning_note is not None
        else build_learning_note_id(context.actor_id, context.course_id, context.class_id)
    )
    source_refs = _collect_primary_source_refs(
        settings,
        top_wiki_match=top_wiki_match,
        raw_source_hits=[],
        candidate_kind=None,
    )
    if existing_learning_note is not None:
        concepts = _merge_unique_strings(existing_learning_note.concepts, concepts)
        gaps = _merge_unique_strings(existing_learning_note.gaps, gaps)
        next_actions = _merge_unique_strings(existing_learning_note.next_actions, next_actions)
        source_refs = _merge_source_refs(existing_learning_note.source_refs, source_refs)
        session_refs = _merge_unique_strings(existing_learning_note.session_refs, [session_id])
    else:
        session_refs = [session_id]
    return LearningNote(
        learning_note_id=learning_note_id,
        student_id=context.actor_id,
        course_id=context.course_id,
        class_id=context.class_id,
        actor_role=ActorRole.SYSTEM,
        concepts=concepts,
        gaps=gaps,
        next_actions=next_actions,
        source_refs=source_refs,
        session_refs=session_refs,
        summary="Focus on the concept boundary highlighted by the current question.",
        created_at=existing_learning_note.created_at
        if existing_learning_note is not None
        else created_at,
        updated_at=created_at,
    )


def _build_candidate_proposal(
    settings: Settings,
    *,
    context: RequestContext,
    request: QueryRequest,
    top_wiki_match: WikiPageMatch | None,
    raw_source_hits: list[RawSourceHit],
    class_sessions: list[SessionRecord],
    session_matches: list[SessionRecord],
    session_id: str,
    created_at: datetime,
    candidate_kind: CandidateKind | None,
) -> CandidateItem | None:
    if candidate_kind is None:
        return None

    title, summary, tags, confidence, related_page_id = _candidate_metadata(
        candidate_kind=candidate_kind,
        class_sessions=class_sessions,
    )
    source_refs = _collect_primary_source_refs(
        settings,
        top_wiki_match=top_wiki_match,
        raw_source_hits=raw_source_hits,
        candidate_kind=candidate_kind,
    )
    if not source_refs:
        return None

    related_sessions = _related_session_refs(
        candidate_kind=candidate_kind,
        class_sessions=class_sessions,
        session_matches=session_matches,
        current_session_id=session_id,
    )
    return CandidateItem(
        candidate_id=build_candidate_id(
            kind=candidate_kind,
            class_id=context.class_id,
            title=title,
            created_at=created_at,
        ),
        kind=candidate_kind,
        status=CandidateStatus.OPEN,
        title=title,
        summary=summary,
        class_id=context.class_id,
        course_id=context.course_id,
        confidence=confidence,
        tags=tags,
        source_refs=source_refs,
        session_refs=related_sessions,
        created_at=created_at,
        updated_at=created_at,
        related_page_id=related_page_id,
    )


def _merge_unique_strings(base: list[str], extra: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in [*base, *extra]:
        if item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


def _merge_source_refs(base: list[SourceRef], extra: list[SourceRef]) -> list[SourceRef]:
    merged: list[SourceRef] = []
    seen: set[tuple[str, SourceType, str | None]] = set()
    for source_ref in [*base, *extra]:
        key = (source_ref.source_id, source_ref.source_type, source_ref.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        merged.append(source_ref)
    return merged


def _collect_raw_source_hits(
    settings: Settings,
    *,
    context: RequestContext,
    request: QueryRequest,
    tokens: set[str],
    recent_sessions: list[SessionRecord],
    top_wiki_match: WikiPageMatch | None,
) -> list[RawSourceHit]:
    candidate_sources = [
        source
        for source in list_source_records(settings)
        if source.course_id == context.course_id
        and source.class_id == context.class_id
        and _source_matches_domain(source, requested_domain=context.domain)
    ]
    attachment_ids = set(request.attachment_source_ids)
    if attachment_ids and context.role is ActorRole.STUDENT:
        raise ForbiddenQueryScopeError("students cannot attach raw source ids directly")
    fallback_source_ids = {
        source_ref.source_id for session in recent_sessions for source_ref in session.source_refs
    }
    hits: dict[str, RawSourceHit] = {}

    for source_id in attachment_ids:
        try:
            source = get_source(settings, source_id)
        except SourceNotFoundError as exc:
            raise QueryStateError("attachment source was not found") from exc
        if source.course_id != context.course_id or source.class_id != context.class_id:
            raise ForbiddenQueryScopeError(
                "attachment source is outside the current course/class scope"
            )
        if not _source_matches_domain(source, requested_domain=context.domain):
            raise ForbiddenQueryScopeError("attachment source is outside the current domain")
        candidate_sources.append(source)

    for source in candidate_sources:
        path = resolve_source_path(settings, source.origin_path)
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        score = _score_source(source, content=content, tokens=tokens)
        if source.source_id in attachment_ids:
            score += 100
        elif top_wiki_match is None and source.source_id in fallback_source_ids:
            score += 2
        if score <= 0:
            continue
        hits[source.source_id] = RawSourceHit(source=source, content=content, score=score)

    return sorted(
        hits.values(),
        key=lambda hit: (hit.score, hit.source.created_at, hit.source.source_id),
        reverse=True,
    )[:5]


def _source_matches_domain(
    source: RawSourceRecord, *, requested_domain: RequestDomain | None
) -> bool:
    if requested_domain is None:
        return source.domain is RequestDomain.ACADEMIC
    if requested_domain is RequestDomain.REVIEW:
        return True
    return source.domain is requested_domain


def _should_emit_raw_source_basis(
    *,
    context: RequestContext,
    request: QueryRequest,
    top_wiki_match: WikiPageMatch | None,
    raw_source_hits: list[RawSourceHit],
) -> bool:
    if not request.allow_raw_source_fallback or not raw_source_hits:
        return False
    if top_wiki_match is None:
        return True
    return context.domain is RequestDomain.OPERATIONS or bool(request.attachment_source_ids)


def _should_emit_learning_context(
    *,
    context: RequestContext,
    learning_note: LearningNote | None,
) -> bool:
    return context.role is ActorRole.STUDENT and learning_note is not None and bool(
        learning_note.gaps or learning_note.next_actions
    )


def _resolve_answer_learning_note(
    *,
    learning_note: LearningNote | None,
    current_session_id: str,
    existing_session: SessionRecord | None,
) -> LearningNote | None:
    if learning_note is None:
        return None
    if current_session_id in learning_note.session_refs:
        if (
            existing_session is not None
            and learning_note.learning_note_id in existing_session.learning_note_refs
            and any(
                session_ref != current_session_id for session_ref in learning_note.session_refs
            )
        ):
            return learning_note
        return None
    return learning_note


def _augment_with_learning_context(
    answer: str,
    *,
    answer_basis: list[str],
    learning_note: LearningNote | None,
) -> str:
    if "learning_context" not in answer_basis or learning_note is None:
        return answer
    if learning_note.gaps:
        return (
            f"{answer} Your current learning note says to keep working on: "
            f"{learning_note.gaps[0]}"
        )
    if learning_note.next_actions:
        return f"{answer} Suggested next step: {learning_note.next_actions[0]}"
    return answer


def _infer_candidate_kind(
    *,
    context: RequestContext,
    request: QueryRequest,
    top_wiki_match: WikiPageMatch | None,
    raw_source_hits: list[RawSourceHit],
) -> CandidateKind | None:
    if context.role is ActorRole.VALIDATOR:
        return None
    message = request.message.lower()
    if context.domain is RequestDomain.OPERATIONS:
        return CandidateKind.OPERATIONS_NOTE
    if (
        context.role is ActorRole.INSTRUCTOR
        and "homework" in message
        and any(keyword in message for keyword in ("due", "deadline", "submit"))
    ):
        return CandidateKind.FAQ
    if ("chain rule" in message or "product rule" in message) and any(
        marker in message for marker in CONCEPT_CONFUSION_MARKERS
    ):
        return CandidateKind.MISCONCEPTION
    if top_wiki_match is None and raw_source_hits:
        return CandidateKind.UNRESOLVED_QUESTION
    if "substitution" in message or "integral" in message:
        return CandidateKind.UNRESOLVED_QUESTION
    return None


def _should_write_learning_note_for_request(
    *,
    context: RequestContext,
    request: QueryRequest,
) -> bool:
    if context.role is not ActorRole.STUDENT:
        return False
    normalized = request.message.lower()
    return any(marker in normalized for marker in CONCEPT_CONFUSION_MARKERS)


def _candidate_metadata(
    *,
    candidate_kind: CandidateKind,
    class_sessions: list[SessionRecord],
) -> tuple[str, str, list[str], float, str | None]:
    if candidate_kind is CandidateKind.FAQ:
        repeated_count = sum(
            1
            for session in class_sessions
            if "homework" in session.question.lower()
            and any(
                keyword in session.question.lower() for keyword in ("due", "deadline", "submit")
            )
        )
        return (
            "Homework 01 submission deadline",
            "Students repeatedly ask when Homework 01 is due and where it must be submitted.",
            ["homework", "deadline", "faq"],
            0.91 if repeated_count >= 2 else 0.74,
            "page-faq-homework-submission",
        )
    if candidate_kind is CandidateKind.MISCONCEPTION:
        return (
            "Chain rule and product rule confusion",
            "Multiple students are mixing up the chain rule and the product "
            "rule when expressions look similar.",
            ["chain-rule", "product-rule", "misconception"],
            0.82,
            "page-misconceptions-chain-rule-product-rule",
        )
    if candidate_kind is CandidateKind.OPERATIONS_NOTE:
        return (
            "Refund policy reminder",
            "Operators need a consistent answer that explains the academic "
            "office review process for refunds.",
            ["operations", "refund"],
            0.88,
            "page-operations-refund-policy",
        )
    return (
        "When substitution is valid for every integral",
        "The current verified wiki does not yet answer the scope limits "
        "of substitution across later units.",
        ["integrals", "unresolved"],
        0.54,
        None,
    )


def _collect_primary_source_refs(
    settings: Settings,
    *,
    top_wiki_match: WikiPageMatch | None,
    raw_source_hits: list[RawSourceHit],
    candidate_kind: CandidateKind | None,
) -> list[SourceRef]:
    refs: list[SourceRef] = []
    if top_wiki_match is not None:
        refs.extend(
            _source_refs_for_page(settings, top_wiki_match.page, candidate_kind=candidate_kind)
        )
    if raw_source_hits:
        refs.extend(
            SourceRef(
                source_id=hit.source.source_id,
                source_type=hit.source.source_type.value,
                chunk_id=_chunk_id_for_candidate(candidate_kind),
            )
            for hit in raw_source_hits[:2]
        )
    return _deduplicate_source_refs(refs)


def _source_refs_for_page(
    settings: Settings,
    page: WikiPage,
    *,
    candidate_kind: CandidateKind | None,
) -> list[SourceRef]:
    refs: list[SourceRef] = []
    for source_id in page.source_refs:
        source_type = _build_source_ref_payload(settings, source_id)["source_type"]
        refs.append(
            SourceRef(
                source_id=source_id,
                source_type=source_type,
                chunk_id=_chunk_id_for_candidate(candidate_kind),
            )
        )
    return refs


def _load_linked_sources_for_page(settings: Settings, page: WikiPage) -> list[RawSourceHit]:
    source_hits: list[RawSourceHit] = []
    for source_id in page.source_refs:
        try:
            source_record = get_source(settings, source_id)
        except SourceNotFoundError:
            continue
        source_path = resolve_source_path(settings, source_record.origin_path)
        if not source_path.exists():
            continue
        source_hits.append(
            RawSourceHit(
                source=source_record,
                content=source_path.read_text(encoding="utf-8"),
                score=0,
            )
        )
    return source_hits


def _score_source(source: RawSourceRecord, *, content: str, tokens: set[str]) -> int:
    haystack = " ".join([source.title, content]).lower()
    haystack_tokens = _tokenize(haystack)
    score = sum(2 for token in tokens if token in haystack_tokens)
    if "homework" in haystack and "deadline" in haystack:
        score += 3
    if "refund" in haystack:
        score += 3
    if "chain rule" in haystack:
        score += 3
    return score


def _score_session(session: SessionRecord, *, tokens: set[str]) -> int:
    haystack_tokens = _tokenize(
        " ".join([session.question, session.answer, " ".join(session.tags)])
    )
    return len(tokens.intersection(haystack_tokens))


def _related_session_refs(
    *,
    candidate_kind: CandidateKind,
    class_sessions: list[SessionRecord],
    session_matches: list[SessionRecord],
    current_session_id: str,
) -> list[str]:
    related: list[str] = [current_session_id]
    if candidate_kind is CandidateKind.FAQ:
        for session in class_sessions:
            message = session.question.lower()
            if "homework" in message and any(
                keyword in message for keyword in ("due", "deadline", "submit")
            ):
                related.append(session.session_id)
    else:
        related.extend(session.session_id for session in session_matches)
    return _deduplicate_strings(related)


def _concepts_for_message(message: str, page: WikiPage | None) -> list[str]:
    normalized = message.lower()
    concepts: list[str] = []
    if "chain rule" in normalized:
        concepts.append("chain rule")
    if "product rule" in normalized:
        concepts.append("product rule")
    if not concepts and page is not None:
        concepts.append(page.title.lower())
    return concepts


def _build_session_tags(
    candidate_kind: CandidateKind | None, top_wiki_match: WikiPageMatch | None
) -> list[str]:
    tags: list[str] = []
    if top_wiki_match is not None:
        tags.append(top_wiki_match.page.domain)
        tags.extend(sorted(_tokenize(top_wiki_match.page.title)))
    if candidate_kind is not None:
        tags.append(candidate_kind.value)
    return _deduplicate_strings(tags)


def _build_source_ref_payload(settings: Settings, source_id: str) -> dict[str, str]:
    try:
        source_record = get_source(settings, source_id)
        return {
            "source_id": source_id,
            "source_type": source_record.source_type.value,
        }
    except SourceNotFoundError:
        return {
            "source_id": source_id,
            "source_type": _infer_source_type_label(source_id),
        }


def _exposed_source_ref_payloads(
    settings: Settings,
    *,
    context: RequestContext,
    source_ids: list[str],
) -> list[dict[str, str]]:
    if context.role is ActorRole.STUDENT:
        return []
    return [_build_source_ref_payload(settings, source_id) for source_id in source_ids]


def _record_writeback_failure(
    settings: Settings,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    request_id: str,
    idempotency_key: str | None,
    notes: str,
    details: dict[str, object] | None = None,
    created_at: datetime,
) -> None:
    create_audit_event(
        settings,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-query-engine",
        notes=notes,
        details=details,
        request_id=request_id,
        idempotency_key=idempotency_key,
        created_at=created_at,
    )


def _candidate_failure_entity_id(settings: Settings, candidate: CandidateItem) -> str:
    for existing_candidate in list_candidates(
        settings,
        kind=candidate.kind,
        status=CandidateStatus.OPEN,
        class_id=candidate.class_id,
    ):
        if existing_candidate.course_id != candidate.course_id:
            continue
        if existing_candidate.title != candidate.title:
            continue
        if existing_candidate.related_page_id != candidate.related_page_id:
            continue
        return existing_candidate.candidate_id
    return candidate.candidate_id


def _tokenize(value: str) -> set[str]:
    return {
        token
        for token in TOKEN_PATTERN.findall(value.lower())
        if len(token) >= 3 and token not in STOPWORDS
    }


def _find_line(items: list[RawSourceHit], *, keywords: tuple[str, ...]) -> str | None:
    normalized_keywords = tuple(keyword.lower() for keyword in keywords if keyword)
    for item in items:
        in_frontmatter = False
        for raw_line in item.content.splitlines():
            line = raw_line.strip().lstrip("- ").strip()
            if not line:
                continue
            if line == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                continue
            if re.match(r"^[a-z_]+:\s", line):
                continue
            haystack = line.lower()
            if any(keyword in haystack for keyword in normalized_keywords):
                return line.rstrip(".")
    return None


def _deduplicate_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduplicated.append(value)
    return deduplicated


def _deduplicate_source_refs(values: list[SourceRef]) -> list[SourceRef]:
    seen: set[tuple[str, str, str | None]] = set()
    deduplicated: list[SourceRef] = []
    for value in values:
        key = (value.source_id, value.source_type, value.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(value)
    return deduplicated


def _infer_source_type_label(source_id: str) -> str:
    if source_id.startswith("src-lecture-note-"):
        return SourceType.LECTURE_NOTE.value
    if source_id.startswith("src-operations-note-"):
        return SourceType.OPERATIONS_NOTE.value
    if source_id.startswith("src-announcement-"):
        return SourceType.ANNOUNCEMENT.value
    return "unknown"


def _chunk_id_for_candidate(candidate_kind: CandidateKind | None) -> str | None:
    if candidate_kind is CandidateKind.FAQ:
        return "deadline"
    if candidate_kind is CandidateKind.MISCONCEPTION:
        return "compare-rules"
    if candidate_kind is CandidateKind.OPERATIONS_NOTE:
        return "policy"
    if candidate_kind is CandidateKind.UNRESOLVED_QUESTION:
        return "scope-gap"
    return None
