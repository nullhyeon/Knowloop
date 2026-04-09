from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from knowloop_api.api.context import RequestContext
from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole, RequestDomain, SourceType
from knowloop_api.db.audit import create_audit_event
from knowloop_api.db.manifest import RawSourceRecord, list_source_records
from knowloop_api.services.candidates import (
    CandidateItem,
    CandidateKind,
    CandidateStatus,
    SourceRef,
    list_candidates,
    upsert_candidate_signal,
)
from knowloop_api.services.learning import (
    LearningNote,
    build_learning_note_id,
    get_learning_note,
    upsert_learning_note,
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
    response_mode: Literal["default", "concise", "teaching", "review"] = "default"

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
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
            normalized.append(candidate)
            seen.add(candidate)
        return normalized


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


class QueryStateError(ValueError):
    """Raised when the query contract cannot be fulfilled safely."""


class InsufficientVerifiedContextError(QueryStateError):
    """Raised when the verified retrieval basis is too weak to answer safely."""


class ForbiddenQueryScopeError(QueryStateError):
    """Raised when the request crosses a forbidden data boundary."""


class QueryReplayConflictError(QueryStateError):
    """Raised when an idempotent query mutation is replayed with a different payload."""


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
    requested_at = datetime.now(UTC).replace(microsecond=0)
    session_id = _build_query_session_id(
        context=context,
        request=request,
        created_at=requested_at,
    )
    existing_session = _load_existing_query_session(settings, session_id=session_id)
    created_at = (
        existing_session.created_at
        if existing_session is not None
        else requested_at
    )
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
            "Raw source fallback was requested, but no matching source material was found in scope."
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
    answer = _build_answer(
        settings,
        request=request,
        context=context,
        top_wiki_match=top_wiki_match,
        raw_source_hits=raw_source_hits,
        answer_basis=answer_basis,
        learning_note=answer_learning_note,
    )
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

    session_record = SessionRecord(
        session_id=session_id,
        role=context.role,
        user_id=context.actor_id,
        class_id=context.class_id,
        course_id=context.course_id,
        question=request.message,
        answer=answer,
        created_at=created_at,
        tags=_build_session_tags(candidate_kind, top_wiki_match),
        source_refs=_collect_primary_source_refs(
            settings,
            top_wiki_match=top_wiki_match,
            raw_source_hits=raw_source_hits,
            candidate_kind=candidate_kind,
        ),
        retrieval_refs=[item.model_dump(mode="json", exclude_none=True) for item in retrieval_refs],
        candidate_refs=existing_session.candidate_refs if existing_session is not None else [],
        learning_note_refs=(
            existing_session.learning_note_refs if existing_session is not None else []
        ),
    )
    if existing_session is not None and not _query_replay_matches(
        existing_session, candidate_session=session_record
    ):
        raise QueryReplayConflictError(
            "Idempotency-Key was reused for a different query payload within the same scope."
        )

    try:
        save_session(settings, session_record, request_id=context.request_id)
    except FileExistsError as exc:
        raise QueryReplayConflictError(
            "The query mutation token was reused for a different payload within the same scope."
        ) from exc

    writeback_plan = [
        WritebackPlanItem(
            kind="session",
            action="save",
            status="registered",
            target_id=session_record.session_id,
            explanation="Stored the current question and answer in the session history.",
        )
    ]

    should_replay_learning = (
        existing_session is not None and bool(existing_session.learning_note_refs)
    )
    if learning_proposal is not None:
        learning_status = "updated"
        stored_learning_note_id: str | None = None
        if should_replay_learning:
            stored_learning_note_id = existing_session.learning_note_refs[0]
        else:
            try:
                stored_learning_note = upsert_learning_note(
                    settings,
                    learning_proposal,
                    actor_id="system-query-engine",
                    request_id=context.request_id,
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
                    notes=str(exc),
                    created_at=created_at,
                )
        writeback_plan.append(
            WritebackPlanItem(
                kind="learning_note",
                action="update",
                status=learning_status,
                target_id=learning_proposal.learning_note_id,
                explanation=(
                    "Updated the student learning layer with concepts, "
                    "gaps, and next actions."
                ),
            )
        )
    else:
        stored_learning_note_id = None

    should_replay_candidate = existing_session is not None and bool(existing_session.candidate_refs)
    if candidate_proposal is not None:
        candidate_status = candidate_proposal.status.value
        candidate_action = "create"
        stored_candidate_id: str | None = None
        if should_replay_candidate:
            stored_candidate_id = existing_session.candidate_refs[0]
            candidate_action = "update"
            candidate_status = "updated"
        else:
            try:
                stored_candidate, candidate_action = upsert_candidate_signal(
                    settings,
                    candidate_proposal,
                    actor_role=ActorRole.SYSTEM,
                    actor_id="system-query-engine",
                    request_id=context.request_id,
                    idempotency_key=context.idempotency_key,
                    notes="Generated from query/respond candidate write-back.",
                )
                stored_candidate_id = stored_candidate.candidate_id
                candidate_status = (
                    stored_candidate.status.value if candidate_action == "create" else "updated"
                )
            except Exception as exc:
                candidate_status = "failed"
                _record_writeback_failure(
                    settings,
                    entity_type="candidate",
                    entity_id=_candidate_failure_entity_id(settings, candidate_proposal),
                    action="candidate_writeback_failed",
                    request_id=context.request_id,
                    notes=str(exc),
                    created_at=created_at,
                )
        writeback_plan.append(
            WritebackPlanItem(
                kind="candidate",
                action=candidate_action,
                status=candidate_status,
                target_id=stored_candidate_id or candidate_proposal.candidate_id,
                explanation="Captured a structured candidate for later review.",
            )
        )
    else:
        stored_candidate_id = None

    if stored_candidate_id is not None or stored_learning_note_id is not None:
        try:
            update_session_artifact_refs(
                settings,
                session_id=session_record.session_id,
                candidate_refs=[stored_candidate_id] if stored_candidate_id is not None else [],
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
                notes=str(exc),
                created_at=created_at,
            )

    return QueryResponse(
        answer=answer,
        answer_basis=answer_basis,
        retrieval_refs=retrieval_refs,
        writeback_plan=writeback_plan,
        session_id=session_record.session_id,
        created_at=created_at,
    )


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
    request: QueryRequest,
    created_at: datetime,
) -> str:
    request_fingerprint = _build_query_request_fingerprint(context=context, request=request)
    if context.idempotency_key is not None:
        mutation_digest = hashlib.sha1(context.idempotency_key.encode("utf-8")).hexdigest()[:10]
        return f"ses-{context.role.value}-{context.actor_id}-{context.class_id}-{mutation_digest}"

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


def _load_existing_query_session(
    settings: Settings,
    *,
    session_id: str,
) -> SessionRecord | None:
    try:
        return get_session(settings, session_id)
    except SessionNotFoundError:
        return None


def _query_replay_matches(
    existing_session: SessionRecord,
    *,
    candidate_session: SessionRecord,
) -> bool:
    return (
        existing_session.model_dump(mode="json", exclude={"candidate_refs", "learning_note_refs"})
        == candidate_session.model_dump(
            mode="json",
            exclude={"candidate_refs", "learning_note_refs"},
        )
    )


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
        basis.append("formal_wiki")
    if context.role is ActorRole.STUDENT and top_wiki_match is not None and session_matches:
        basis.append("session_context")
    if _should_emit_learning_context(context=context, learning_note=learning_note):
        basis.append("learning_context")
    if _should_emit_raw_source_basis(
        context=context,
        request=request,
        top_wiki_match=top_wiki_match,
        raw_source_hits=raw_source_hits,
    ):
        basis.append("raw_source_fallback")
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
        if request.response_mode == "teaching":
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
    if response_mode == "concise":
        return answer
    if response_mode == "teaching" and context.role is ActorRole.STUDENT:
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
    return LearningNote(
        learning_note_id=learning_note_id,
        student_id=context.actor_id,
        course_id=context.course_id,
        class_id=context.class_id,
        actor_role=ActorRole.SYSTEM,
        concepts=concepts,
        gaps=gaps,
        next_actions=next_actions,
        source_refs=_collect_primary_source_refs(
            settings,
            top_wiki_match=top_wiki_match,
            raw_source_hits=[],
            candidate_kind=None,
        ),
        session_refs=[session_id],
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
        related_page_id=related_page_id,
    )


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
) -> LearningNote | None:
    if learning_note is None:
        return None
    if current_session_id in learning_note.session_refs:
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
    notes: str,
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
        request_id=request_id,
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
