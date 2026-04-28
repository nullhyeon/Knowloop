from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import (
    ActorRole,
    validate_actor_id,
    validate_class_id,
    validate_course_id,
)
from knowloop_api.db.audit import create_audit_event, list_audit_events
from knowloop_api.db.sqlite import connect_sqlite
from knowloop_api.services.candidates import SourceRef


class SessionRecord(BaseModel):
    session_id: str
    role: ActorRole
    user_id: str
    class_id: str
    course_id: str
    question: str
    answer: str
    created_at: datetime
    tags: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    retrieval_refs: list[dict[str, object]] = Field(default_factory=list)
    candidate_refs: list[str] = Field(default_factory=list)
    learning_note_refs: list[str] = Field(default_factory=list)
    replay_intent: dict[str, object] | None = None


class SessionInsightRow(BaseModel):
    session_id: str
    user_id: str
    tags: list[str] = Field(default_factory=list)


class SessionNotFoundError(FileNotFoundError):
    """Raised when a session cannot be found in storage."""


def save_session(
    settings: Settings,
    session: SessionRecord,
    *,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    details: dict[str, object] | None = None,
    raise_on_existing: bool = False,
) -> SessionRecord:
    validate_actor_id(session.user_id, actor_role=session.role)
    validate_course_id(session.course_id)
    validate_class_id(session.class_id)

    with connect_sqlite(settings.sessions_db_path) as connection:
        existing_row = connection.execute(
            """
            SELECT
                session_id,
                role,
                user_id,
                class_id,
                course_id,
                question,
                answer,
                created_at,
                tags_json,
                source_refs_json,
                retrieval_refs_json,
                candidate_refs_json,
                learning_note_refs_json,
                replay_intent_json
            FROM sessions
            WHERE session_id = ?
            """,
            (session.session_id,),
        ).fetchone()
        if existing_row is not None:
            existing = _session_from_row(existing_row)
            if existing != session or raise_on_existing:
                raise FileExistsError(f"session already exists: {session.session_id}")
            _ensure_session_saved_audit(
                settings,
                session=session,
                request_id=request_id,
                idempotency_key=idempotency_key,
                details=details,
            )
            return existing

        try:
            connection.execute(
                """
                INSERT INTO sessions (
                    session_id,
                    role,
                    user_id,
                    class_id,
                    course_id,
                    question,
                    answer,
                    created_at,
                    tags_json,
                    source_refs_json,
                    retrieval_refs_json,
                    candidate_refs_json,
                    learning_note_refs_json,
                    replay_intent_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.role.value,
                    session.user_id,
                    session.class_id,
                    session.course_id,
                    session.question,
                    session.answer,
                    _serialize_timestamp(session.created_at),
                    json.dumps(session.tags, ensure_ascii=False),
                    json.dumps(
                        [
                            source_ref.model_dump(mode="json", exclude_none=True)
                            for source_ref in session.source_refs
                        ],
                        ensure_ascii=False,
                    ),
                    json.dumps(session.retrieval_refs, ensure_ascii=False),
                    json.dumps(session.candidate_refs, ensure_ascii=False),
                    json.dumps(session.learning_note_refs, ensure_ascii=False),
                    json.dumps(session.replay_intent, ensure_ascii=False),
                ),
            )
        except sqlite3.IntegrityError as exc:
            existing = get_session(settings, session.session_id)
            if existing == session and not raise_on_existing:
                _ensure_session_saved_audit(
                    settings,
                    session=session,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    details=details,
                )
                return existing
            raise FileExistsError(f"session already exists: {session.session_id}") from exc
        connection.commit()

    _write_session_export(settings, session)
    _ensure_session_saved_audit(
        settings,
        session=session,
        request_id=request_id,
        idempotency_key=idempotency_key,
        details=details,
    )
    return session


def _ensure_session_saved_audit(
    settings: Settings,
    *,
    session: SessionRecord,
    request_id: str | None,
    idempotency_key: str | None,
    details: dict[str, object] | None,
) -> None:
    existing_events = list_audit_events(
        settings,
        entity_type="session",
        entity_id=session.session_id,
        action="session_saved",
    )

    if idempotency_key is not None:
        if any(event.idempotency_key == idempotency_key for event in existing_events):
            return
    elif request_id is not None:
        if any(event.request_id == request_id for event in existing_events):
            return
    elif existing_events:
        return

    create_audit_event(
        settings,
        entity_type="session",
        entity_id=session.session_id,
        action="session_saved",
        actor_role=session.role.value,
        actor_id=session.user_id,
        details=details,
        request_id=request_id,
        idempotency_key=idempotency_key,
        created_at=session.created_at,
    )


def get_session(settings: Settings, session_id: str) -> SessionRecord:
    with connect_sqlite(settings.sessions_db_path) as connection:
        row = connection.execute(
            """
            SELECT
                session_id,
                role,
                user_id,
                class_id,
                course_id,
                question,
                answer,
                created_at,
                tags_json,
                source_refs_json,
                retrieval_refs_json,
                candidate_refs_json,
                learning_note_refs_json,
                replay_intent_json
            FROM sessions
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

    if row is None:
        raise SessionNotFoundError(session_id)
    return _session_from_row(row)


def list_recent_sessions(
    settings: Settings,
    *,
    user_id: str,
    class_id: str,
    course_id: str,
    limit: int = 5,
) -> list[SessionRecord]:
    with connect_sqlite(settings.sessions_db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                session_id,
                role,
                user_id,
                class_id,
                course_id,
                question,
                answer,
                created_at,
                tags_json,
                source_refs_json,
                retrieval_refs_json,
                candidate_refs_json,
                learning_note_refs_json,
                replay_intent_json
            FROM sessions
            WHERE user_id = ?
              AND class_id = ?
              AND course_id = ?
            ORDER BY created_at DESC, session_id DESC
            LIMIT ?
            """,
            (user_id, class_id, course_id, limit),
        ).fetchall()

    return [_session_from_row(row) for row in rows]


def list_sessions_for_class(
    settings: Settings,
    *,
    class_id: str,
    course_id: str,
    role: ActorRole | None = None,
    limit: int = 100,
) -> list[SessionRecord]:
    parameters: list[object] = [class_id, course_id]
    role_clause = ""
    if role is not None:
        role_clause = " AND role = ?"
        parameters.append(role.value)
    parameters.append(limit)

    with connect_sqlite(settings.sessions_db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                session_id,
                role,
                user_id,
                class_id,
                course_id,
                question,
                answer,
                created_at,
                tags_json,
                source_refs_json,
                retrieval_refs_json,
                candidate_refs_json,
                learning_note_refs_json,
                replay_intent_json
            FROM sessions
            WHERE class_id = ?
              AND course_id = ?
              {role_clause}
            ORDER BY created_at DESC, session_id DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()

    return [_session_from_row(row) for row in rows]


def list_session_insight_rows_for_class(
    settings: Settings,
    *,
    class_id: str,
    course_id: str,
    role: ActorRole | None = None,
) -> list[SessionInsightRow]:
    parameters: list[object] = [class_id, course_id]
    role_clause = ""
    if role is not None:
        role_clause = " AND role = ?"
        parameters.append(role.value)

    with connect_sqlite(settings.sessions_db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                session_id,
                user_id,
                tags_json
            FROM sessions
            WHERE class_id = ?
              AND course_id = ?
              {role_clause}
            ORDER BY created_at DESC, session_id DESC
            """,
            parameters,
        ).fetchall()

    return [
        SessionInsightRow(
            session_id=str(row[0]),
            user_id=str(row[1]),
            tags=json.loads(str(row[2])),
        )
        for row in rows
    ]


def update_session_artifact_refs(
    settings: Settings,
    *,
    session_id: str,
    candidate_refs: list[str],
    learning_note_refs: list[str],
) -> SessionRecord:
    session = get_session(settings, session_id)
    updated_session = session.model_copy(
        update={
            "candidate_refs": _merge_unique_strings(session.candidate_refs, candidate_refs),
            "learning_note_refs": _merge_unique_strings(
                session.learning_note_refs,
                learning_note_refs,
            ),
        }
    )

    with connect_sqlite(settings.sessions_db_path) as connection:
        connection.execute(
            """
            UPDATE sessions
            SET candidate_refs_json = ?, learning_note_refs_json = ?
            WHERE session_id = ?
            """,
            (
                json.dumps(updated_session.candidate_refs, ensure_ascii=False),
                json.dumps(updated_session.learning_note_refs, ensure_ascii=False),
                session_id,
            ),
        )
        connection.commit()

    _write_session_export(settings, updated_session)
    return updated_session


def update_session_replay_intent(
    settings: Settings,
    *,
    session_id: str,
    replay_intent: dict[str, object] | None,
) -> SessionRecord:
    session = get_session(settings, session_id)
    updated_session = session.model_copy(update={"replay_intent": replay_intent})

    with connect_sqlite(settings.sessions_db_path) as connection:
        connection.execute(
            """
            UPDATE sessions
            SET replay_intent_json = ?
            WHERE session_id = ?
            """,
            (
                json.dumps(replay_intent, ensure_ascii=False),
                session_id,
            ),
        )
        connection.commit()

    _write_session_export(settings, updated_session)
    return updated_session


def build_session_id(
    *,
    role: ActorRole,
    user_id: str,
    class_id: str,
    created_at: datetime,
) -> str:
    timestamp = created_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"ses-{role.value}-{user_id}-{class_id}-{timestamp}"


def build_session_export_path(settings: Settings, session: SessionRecord) -> Path:
    return (
        settings.data_root
        / "sessions"
        / session.role.value
        / session.class_id
        / session.user_id
        / f"{session.session_id}.json"
    )


def _write_session_export(settings: Settings, session: SessionRecord) -> None:
    path = build_session_export_path(settings, session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(session.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def _session_from_row(row: tuple[object, ...]) -> SessionRecord:
    return SessionRecord(
        session_id=str(row[0]),
        role=ActorRole(str(row[1])),
        user_id=str(row[2]),
        class_id=str(row[3]),
        course_id=str(row[4]),
        question=str(row[5]),
        answer=str(row[6]),
        created_at=_parse_timestamp(str(row[7])),
        tags=json.loads(str(row[8])),
        source_refs=[SourceRef.model_validate(item) for item in json.loads(str(row[9]))],
        retrieval_refs=json.loads(str(row[10])),
        candidate_refs=json.loads(str(row[11])),
        learning_note_refs=json.loads(str(row[12])),
        replay_intent=(
            json.loads(str(row[13])) if row[13] is not None else None
        ),
    )


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _serialize_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _merge_unique_strings(base: list[str], extra: list[str]) -> list[str]:
    seen = set(base)
    merged = list(base)
    for item in extra:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged
