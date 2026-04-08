from __future__ import annotations

import sqlite3
from pathlib import Path

from knowloop_api.core.config import Settings

SESSIONS_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        role TEXT NOT NULL,
        user_id TEXT NOT NULL,
        class_id TEXT NOT NULL,
        course_id TEXT NOT NULL,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        created_at TEXT NOT NULL,
        tags_json TEXT NOT NULL DEFAULT '[]',
        source_refs_json TEXT NOT NULL DEFAULT '[]',
        retrieval_refs_json TEXT NOT NULL DEFAULT '[]',
        candidate_refs_json TEXT NOT NULL DEFAULT '[]',
        learning_note_refs_json TEXT NOT NULL DEFAULT '[]'
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sessions_user_class_created_at
    ON sessions (user_id, class_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sessions_course_class_created_at
    ON sessions (course_id, class_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sessions_role_created_at
    ON sessions (role, created_at)
    """,
]

AUDIT_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        event_id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        action TEXT NOT NULL,
        actor_role TEXT NOT NULL,
        actor_id TEXT,
        from_status TEXT,
        to_status TEXT,
        notes TEXT,
        request_id TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_entity_created_at
    ON audit_events (entity_type, entity_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_action_created_at
    ON audit_events (action, created_at)
    """,
]


def bootstrap_storage(settings: Settings) -> None:
    settings.data_root.mkdir(parents=True, exist_ok=True)
    settings.meta_root.mkdir(parents=True, exist_ok=True)

    _bootstrap_sqlite_database(settings.sessions_db_path, SESSIONS_SCHEMA_STATEMENTS)
    _bootstrap_sqlite_database(settings.audit_db_path, AUDIT_SCHEMA_STATEMENTS)


def build_storage_readiness_payload(settings: Settings) -> dict[str, object]:
    checks = {
        "data_root": _status_for_path(settings.data_root),
        "sessions_db": _status_for_database(settings.sessions_db_path, {"sessions"}),
        "audit_db": _status_for_database(settings.audit_db_path, {"audit_events"}),
    }
    status = "ready" if all(value == "ok" for value in checks.values()) else "not_ready"
    return {
        "status": status,
        "checks": checks,
    }


def _bootstrap_sqlite_database(path: Path, statements: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for statement in statements:
            connection.execute(statement)
        connection.commit()


def _status_for_path(path: Path) -> str:
    return "ok" if path.exists() else "missing"


def _status_for_database(path: Path, required_tables: set[str]) -> str:
    if not path.exists():
        return "missing"

    existing_tables = _fetch_table_names(path)
    return "ok" if required_tables.issubset(existing_tables) else "missing"


def _fetch_table_names(path: Path) -> set[str]:
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()

    return {row[0] for row in rows}
