from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole
from knowloop_api.services.sessions import (
    SessionRecord,
    list_recent_sessions,
    list_sessions_for_class,
)

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "about",
    "again",
    "also",
    "and",
    "are",
    "because",
    "class",
    "does",
    "from",
    "have",
    "homework",
    "into",
    "just",
    "not",
    "our",
    "same",
    "test",
    "that",
    "the",
    "their",
    "them",
    "they",
    "this",
    "when",
    "where",
    "with",
    "would",
    "your",
}


class SessionVisibility(StrEnum):
    OWN = "own"
    CLASS_REDACTED = "class_redacted"


class SessionSearchHit(BaseModel):
    session_id: str
    role: ActorRole
    created_at: str
    tags: list[str]
    candidate_ref_count: int
    learning_note_ref_count: int
    source_ref_count: int
    visibility: SessionVisibility
    match_summary: str
    question_preview: str | None = None
    answer_preview: str | None = None


class ForbiddenSessionSearchError(ValueError):
    """Raised when a role cannot use the session search routes."""


def search_sessions(
    settings: Settings,
    *,
    role: ActorRole,
    actor_id: str,
    course_id: str,
    class_id: str,
    query: str,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[SessionSearchHit], int]:
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be blank")

    sessions = _load_visible_sessions(
        settings,
        role=role,
        actor_id=actor_id,
        course_id=course_id,
        class_id=class_id,
    )
    tokens = _tokenize(normalized_query)
    scored_sessions = [
        (session, _score_session(session, tokens=tokens, normalized_query=normalized_query.lower()))
        for session in sessions
    ]
    matches = [
        _build_search_hit(
            session,
            viewer_role=role,
            match_count=score,
        )
        for session, score in sorted(
            (item for item in scored_sessions if item[1] > 0),
            key=lambda item: (item[1], item[0].created_at, item[0].session_id),
            reverse=True,
        )
    ]
    total = len(matches)
    return matches[offset : offset + limit], total


def list_recent_session_hits(
    settings: Settings,
    *,
    role: ActorRole,
    actor_id: str,
    course_id: str,
    class_id: str,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[SessionSearchHit], int]:
    sessions = _load_visible_sessions(
        settings,
        role=role,
        actor_id=actor_id,
        course_id=course_id,
        class_id=class_id,
    )
    ordered_sessions = sorted(
        sessions,
        key=lambda session: (session.created_at, session.session_id),
        reverse=True,
    )
    total = len(ordered_sessions)
    return [
        _build_search_hit(session, viewer_role=role)
        for session in ordered_sessions[offset : offset + limit]
    ], total


def _load_visible_sessions(
    settings: Settings,
    *,
    role: ActorRole,
    actor_id: str,
    course_id: str,
    class_id: str,
) -> list[SessionRecord]:
    if role in {ActorRole.STUDENT, ActorRole.OPERATOR}:
        return list_recent_sessions(
            settings,
            user_id=actor_id,
            class_id=class_id,
            course_id=course_id,
            limit=200,
        )
    if role is ActorRole.INSTRUCTOR:
        return list_sessions_for_class(
            settings,
            class_id=class_id,
            course_id=course_id,
            role=ActorRole.STUDENT,
            limit=500,
        )
    raise ForbiddenSessionSearchError("This role cannot access the session search routes.")


def _build_search_hit(
    session: SessionRecord,
    *,
    viewer_role: ActorRole,
    match_count: int | None = None,
) -> SessionSearchHit:
    if viewer_role is ActorRole.INSTRUCTOR:
        visibility = SessionVisibility.CLASS_REDACTED
        question_preview = None
        answer_preview = None
        if match_count is None:
            match_summary = "Recent student session in the current class."
        else:
            match_summary = f"Matched {match_count} indexed terms in a student session."
    else:
        visibility = SessionVisibility.OWN
        question_preview = _truncate_preview(session.question)
        answer_preview = _truncate_preview(session.answer)
        if match_count is None:
            match_summary = "Recent session from your scoped history."
        else:
            match_summary = f"Matched {match_count} indexed terms in your scoped history."

    return SessionSearchHit(
        session_id=session.session_id,
        role=session.role,
        created_at=session.created_at.isoformat().replace("+00:00", "Z"),
        tags=session.tags,
        candidate_ref_count=len(session.candidate_refs),
        learning_note_ref_count=len(session.learning_note_refs),
        source_ref_count=len(session.source_refs),
        visibility=visibility,
        match_summary=match_summary,
        question_preview=question_preview,
        answer_preview=answer_preview,
    )


def _score_session(
    session: SessionRecord,
    *,
    tokens: set[str],
    normalized_query: str,
) -> int:
    haystack = " ".join(
        [
            session.question.lower(),
            session.answer.lower(),
            " ".join(session.tags).lower(),
        ]
    )
    haystack_tokens = _tokenize(haystack)
    score = 0
    for token in tokens:
        if token in haystack_tokens:
            score += 3
        if token in {tag.lower() for tag in session.tags}:
            score += 2
    if normalized_query and normalized_query in haystack:
        score += 4
    return score


def _tokenize(value: str) -> set[str]:
    return {
        token
        for token in TOKEN_PATTERN.findall(value.lower())
        if len(token) >= 3 and token not in STOPWORDS
    }


def _truncate_preview(value: str, *, limit: int = 140) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."
