from __future__ import annotations

import sqlite3
from pathlib import Path

from knowloop_api.core.config import Settings
from knowloop_api.db.manifest import ensure_manifest_exists, manifest_status

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
        idempotency_key TEXT,
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
    """
    CREATE TABLE IF NOT EXISTS mutation_requests (
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        action TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        actor_role TEXT NOT NULL,
        actor_id TEXT,
        request_fingerprint TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (entity_type, entity_id, action, idempotency_key)
    )
    """,
]

SESSIONS_MIGRATION_COLUMN_DEFINITIONS = {
    "tags_json": "TEXT NOT NULL DEFAULT '[]'",
    "source_refs_json": "TEXT NOT NULL DEFAULT '[]'",
    "retrieval_refs_json": "TEXT NOT NULL DEFAULT '[]'",
    "candidate_refs_json": "TEXT NOT NULL DEFAULT '[]'",
    "learning_note_refs_json": "TEXT NOT NULL DEFAULT '[]'",
}

AUDIT_EVENT_MIGRATION_COLUMN_DEFINITIONS = {
    "actor_id": "TEXT",
    "from_status": "TEXT",
    "to_status": "TEXT",
    "notes": "TEXT",
    "request_id": "TEXT",
    "idempotency_key": "TEXT",
}

MUTATION_REQUEST_MIGRATION_COLUMN_DEFINITIONS = {
    "actor_role": "TEXT NOT NULL DEFAULT 'system'",
    "actor_id": "TEXT",
    "request_fingerprint": "TEXT NOT NULL DEFAULT ''",
    "status": "TEXT NOT NULL DEFAULT 'pending'",
    "created_at": "TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z'",
    "updated_at": "TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z'",
}

SESSIONS_REQUIRED_COLUMNS = {
    "session_id",
    "role",
    "user_id",
    "class_id",
    "course_id",
    "question",
    "answer",
    "created_at",
    "tags_json",
    "source_refs_json",
    "retrieval_refs_json",
    "candidate_refs_json",
    "learning_note_refs_json",
}

AUDIT_REQUIRED_COLUMNS = {
    "event_id",
    "entity_type",
    "entity_id",
    "action",
    "actor_role",
    "actor_id",
    "from_status",
    "to_status",
    "notes",
    "request_id",
    "idempotency_key",
    "created_at",
}

MUTATION_REQUEST_REQUIRED_COLUMNS = {
    "entity_type",
    "entity_id",
    "action",
    "idempotency_key",
    "actor_role",
    "actor_id",
    "request_fingerprint",
    "status",
    "created_at",
    "updated_at",
}

SESSIONS_REQUIRED_PRIMARY_KEY = ("session_id",)
AUDIT_REQUIRED_PRIMARY_KEY = ("event_id",)
MUTATION_REQUEST_REQUIRED_PRIMARY_KEY = (
    "entity_type",
    "entity_id",
    "action",
    "idempotency_key",
)


def bootstrap_storage(settings: Settings) -> None:
    settings.data_root.mkdir(parents=True, exist_ok=True)
    settings.meta_root.mkdir(parents=True, exist_ok=True)
    ensure_manifest_exists(settings)

    _bootstrap_sqlite_database(settings.sessions_db_path, SESSIONS_SCHEMA_STATEMENTS)
    _bootstrap_sqlite_database(settings.audit_db_path, AUDIT_SCHEMA_STATEMENTS)


def build_storage_readiness_payload(settings: Settings) -> dict[str, object]:
    checks = {
        "data_root": _status_for_path(settings.data_root),
        "manifest": manifest_status(settings),
        "sessions_db": _status_for_database(
            settings.sessions_db_path,
            table_columns={"sessions": SESSIONS_REQUIRED_COLUMNS},
            table_primary_keys={"sessions": SESSIONS_REQUIRED_PRIMARY_KEY},
        ),
        "audit_db": _status_for_database(
            settings.audit_db_path,
            table_columns={
                "audit_events": AUDIT_REQUIRED_COLUMNS,
                "mutation_requests": MUTATION_REQUEST_REQUIRED_COLUMNS,
            },
            table_primary_keys={
                "audit_events": AUDIT_REQUIRED_PRIMARY_KEY,
                "mutation_requests": MUTATION_REQUEST_REQUIRED_PRIMARY_KEY,
            },
        ),
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
        _ensure_table_columns(
            connection,
            "sessions",
            SESSIONS_MIGRATION_COLUMN_DEFINITIONS,
        )
        _ensure_table_columns(
            connection,
            "audit_events",
            AUDIT_EVENT_MIGRATION_COLUMN_DEFINITIONS,
        )
        _ensure_table_columns(
            connection,
            "mutation_requests",
            MUTATION_REQUEST_MIGRATION_COLUMN_DEFINITIONS,
        )
        connection.commit()


def _status_for_path(path: Path) -> str:
    return "ok" if path.exists() else "missing"


def _status_for_database(
    path: Path,
    *,
    table_columns: dict[str, set[str]],
    table_primary_keys: dict[str, tuple[str, ...]],
) -> str:
    if not path.exists():
        return "missing"

    try:
        existing_tables = _fetch_table_names(path)
        if not set(table_columns).issubset(existing_tables):
            return "missing"

        with sqlite3.connect(path) as connection:
            for table_name, required_columns in table_columns.items():
                if not required_columns.issubset(_fetch_table_columns(connection, table_name)):
                    return "missing"
            for table_name, required_primary_key in table_primary_keys.items():
                if _fetch_primary_key_columns(connection, table_name) != required_primary_key:
                    return "missing"
        return "ok"
    except sqlite3.DatabaseError:
        return "missing"


def _fetch_table_names(path: Path) -> set[str]:
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()

    return {row[0] for row in rows}


def _ensure_table_columns(
    connection: sqlite3.Connection,
    table_name: str,
    column_definitions: dict[str, str],
) -> None:
    if not _table_exists(connection, table_name):
        return

    columns = _fetch_table_columns(connection, table_name)
    for column_name, column_definition in column_definitions.items():
        if column_name not in columns:
            connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
            )


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _fetch_table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _fetch_primary_key_columns(
    connection: sqlite3.Connection, table_name: str
) -> tuple[str, ...]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    primary_key_rows = sorted(
        (row for row in rows if row[5] > 0),
        key=lambda row: row[5],
    )
    return tuple(row[1] for row in primary_key_rows)
