from __future__ import annotations

import sqlite3
from enum import StrEnum

from pydantic import BaseModel

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole
from knowloop_api.services.sessions import (
    SessionRecord,
    _session_from_row,
    list_recent_sessions,
    list_sessions_for_class,
)

STOPWORDS = {
    "about",
    "again",
    "all",
    "also",
    "and",
    "are",
    "because",
    "but",
    "class",
    "does",
    "for",
    "from",
    "have",
    "how",
    "into",
    "just",
    "let",
    "not",
    "our",
    "same",
    "test",
    "than",
    "that",
    "the",
    "their",
    "them",
    "they",
    "this",
    "too",
    "what",
    "when",
    "where",
    "were",
    "will",
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

    hits, total = _search_visible_sessions_with_index(
        settings,
        role=role,
        actor_id=actor_id,
        course_id=course_id,
        class_id=class_id,
        query=normalized_query,
        limit=limit,
        offset=offset,
    )
    return hits, total


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


def _build_scope_filter(
    *,
    role: ActorRole,
    actor_id: str,
    course_id: str,
    class_id: str,
) -> tuple[str, list[object]]:
    if role in {ActorRole.STUDENT, ActorRole.OPERATOR}:
        return "s.user_id = ? AND s.class_id = ? AND s.course_id = ?", [
            actor_id,
            class_id,
            course_id,
        ]
    if role is ActorRole.INSTRUCTOR:
        return "s.class_id = ? AND s.course_id = ? AND s.role = ?", [
            class_id,
            course_id,
            ActorRole.STUDENT.value,
        ]
    raise ForbiddenSessionSearchError("This role cannot access the session search routes.")


def _search_visible_sessions_with_index(
    settings: Settings,
    *,
    role: ActorRole,
    actor_id: str,
    course_id: str,
    class_id: str,
    query: str,
    limit: int,
    offset: int,
) -> tuple[list[SessionSearchHit], int]:
    fts_query = _build_fts_query(query)
    if fts_query is None:
        hits, total = _search_visible_sessions_fallback(
            settings,
            role=role,
            actor_id=actor_id,
            course_id=course_id,
            class_id=class_id,
            query=query,
            limit=limit,
            offset=offset,
        )
        return hits, total

    filter_clause, base_parameters = _build_scope_filter(
        role=role,
        actor_id=actor_id,
        course_id=course_id,
        class_id=class_id,
    )

    with sqlite3.connect(settings.sessions_db_path) as connection:
        count_row = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM sessions_fts
            JOIN sessions AS s
              ON s.rowid = sessions_fts.rowid
            WHERE {filter_clause}
              AND sessions_fts MATCH ?
            """,
            [*base_parameters, fts_query],
        ).fetchone()
        rows = connection.execute(
            f"""
            SELECT
                s.session_id,
                s.role,
                s.user_id,
                s.class_id,
                s.course_id,
                s.question,
                s.answer,
                s.created_at,
                s.tags_json,
                s.source_refs_json,
                s.retrieval_refs_json,
                s.candidate_refs_json,
                s.learning_note_refs_json,
                s.replay_intent_json,
                bm25(sessions_fts, 8.0, 3.0, 2.0) AS rank_score
            FROM sessions_fts
            JOIN sessions AS s
              ON s.rowid = sessions_fts.rowid
            WHERE {filter_clause}
              AND sessions_fts MATCH ?
            ORDER BY rank_score ASC, s.created_at DESC, s.session_id DESC
            LIMIT ? OFFSET ?
            """,
            [*base_parameters, fts_query, limit, offset],
        ).fetchall()

    match_count = _match_token_count(query)
    hits = [
        _build_search_hit(
            _session_from_row(row[:14]),
            viewer_role=role,
            match_count=match_count,
        )
        for row in rows
    ]
    return hits, int(count_row[0] if count_row is not None else 0)


def _search_visible_sessions_fallback(
    settings: Settings,
    *,
    role: ActorRole,
    actor_id: str,
    course_id: str,
    class_id: str,
    query: str,
    limit: int,
    offset: int,
) -> tuple[list[SessionSearchHit], int]:
    normalized_query = query.lower()
    filter_clause, base_parameters = _build_scope_filter(
        role=role,
        actor_id=actor_id,
        course_id=course_id,
        class_id=class_id,
    )
    like_pattern = f"%{normalized_query}%"

    with sqlite3.connect(settings.sessions_db_path) as connection:
        count_row = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM sessions AS s
            WHERE {filter_clause}
              AND (
                LOWER(s.question) LIKE ?
                OR LOWER(s.answer) LIKE ?
                OR LOWER(s.tags_json) LIKE ?
              )
            """,
            [*base_parameters, like_pattern, like_pattern, like_pattern],
        ).fetchone()
        rows = connection.execute(
            f"""
            SELECT
                s.session_id,
                s.role,
                s.user_id,
                s.class_id,
                s.course_id,
                s.question,
                s.answer,
                s.created_at,
                s.tags_json,
                s.source_refs_json,
                s.retrieval_refs_json,
                s.candidate_refs_json,
                s.learning_note_refs_json,
                s.replay_intent_json
            FROM sessions AS s
            WHERE {filter_clause}
              AND (
                LOWER(s.question) LIKE ?
                OR LOWER(s.answer) LIKE ?
                OR LOWER(s.tags_json) LIKE ?
              )
            ORDER BY s.created_at DESC, s.session_id DESC
            LIMIT ? OFFSET ?
            """,
            [*base_parameters, like_pattern, like_pattern, like_pattern, limit, offset],
        ).fetchall()

    total = int(count_row[0] if count_row is not None else 0)
    return [
        _build_search_hit(
            _session_from_row(row),
            viewer_role=role,
            match_count=1,
        )
        for row in rows
    ], total


def _build_fts_query(value: str) -> str | None:
    normalized = " ".join(value.lower().split())
    if not normalized:
        return None

    tokens: list[str] = []
    for raw_token in normalized.split():
        token = raw_token.strip("\"'()[]{}:;,.!?")
        if len(token) < 2 or token in STOPWORDS:
            continue
        escaped = token.replace('"', '""')
        tokens.append(f'"{escaped}"*')

    if not tokens:
        return None
    return " AND ".join(tokens)


def _match_token_count(value: str) -> int:
    return max(
        len(
            [
                token
                for token in (" ".join(value.lower().split())).split()
                if len(token.strip("\"'()[]{}:;,.!?")) >= 2
                and token.strip("\"'()[]{}:;,.!?") not in STOPWORDS
            ]
        ),
        1,
    )


def _truncate_preview(value: str, *, limit: int = 140) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."
