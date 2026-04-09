import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from knowloop_api.core.config import Settings
from knowloop_api.db.bootstrap import bootstrap_storage, build_storage_readiness_payload
from knowloop_api.main import create_app


def build_settings(tmp_path: Path) -> Settings:
    data_root = tmp_path / "data"
    return Settings(
        data_root=data_root,
    )


def build_client(tmp_path: Path) -> tuple[TestClient, Settings]:
    settings = build_settings(tmp_path)
    return TestClient(create_app(settings)), settings


def read_table_names(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()

    return {row[0] for row in rows}


def read_table_columns(database_path: Path, table_name: str) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()

    return {row[1] for row in rows}


def test_root_endpoint_reports_service_status(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_process_health_endpoint_is_available(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_health_endpoint_is_available(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get("/api/v1/system/health")

    assert response.status_code == 200
    assert response.json() == {
        "request_id": "system-health",
        "data": {"status": "ok"},
        "meta": {},
    }


def test_storage_bootstrap_creates_expected_databases_and_tables(tmp_path: Path) -> None:
    _client, settings = build_client(tmp_path)

    assert (settings.meta_root / "manifest.json").exists()
    assert settings.sessions_db_path.exists()
    assert settings.audit_db_path.exists()
    assert {"sessions"}.issubset(read_table_names(settings.sessions_db_path))
    assert {"audit_events", "mutation_requests"}.issubset(read_table_names(settings.audit_db_path))
    assert {"request_id", "idempotency_key"}.issubset(
        read_table_columns(settings.audit_db_path, "audit_events")
    )


def test_storage_bootstrap_migrates_legacy_storage_columns(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    settings.meta_root.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(settings.sessions_db_path) as connection:
        connection.execute(
            """
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                user_id TEXT NOT NULL,
                class_id TEXT NOT NULL,
                course_id TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()

    with sqlite3.connect(settings.audit_db_path) as connection:
        connection.execute(
            """
            CREATE TABLE audit_events (
                event_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                actor_id TEXT,
                from_status TEXT,
                to_status TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE mutation_requests (
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                PRIMARY KEY (entity_type, entity_id, action, idempotency_key)
            )
            """
        )
        connection.commit()

    bootstrap_storage(settings)

    assert {
        "tags_json",
        "source_refs_json",
        "retrieval_refs_json",
        "candidate_refs_json",
        "learning_note_refs_json",
    }.issubset(read_table_columns(settings.sessions_db_path, "sessions"))
    assert {"audit_events", "mutation_requests"}.issubset(read_table_names(settings.audit_db_path))
    assert {"request_id", "idempotency_key"}.issubset(
        read_table_columns(settings.audit_db_path, "audit_events")
    )
    assert {
        "actor_role",
        "actor_id",
        "request_fingerprint",
        "status",
        "created_at",
        "updated_at",
    }.issubset(read_table_columns(settings.audit_db_path, "mutation_requests"))


def test_settings_derive_storage_paths_from_data_root(tmp_path: Path) -> None:
    data_root = tmp_path / "custom-data-root"

    settings = Settings(data_root=data_root)

    assert settings.meta_root == data_root / "meta"
    assert settings.sessions_db_path == data_root / "meta" / "sessions.db"
    assert settings.audit_db_path == data_root / "meta" / "audit.db"


def test_readiness_endpoints_report_storage_checks(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get("/readyz")
    api_response = client.get("/api/v1/system/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {
            "data_root": "ok",
            "manifest": "ok",
            "sessions_db": "ok",
            "audit_db": "ok",
        },
    }
    assert api_response.status_code == 200
    assert api_response.json() == {
        "request_id": "system-ready",
        "data": {
            "status": "ready",
            "checks": {
                "data_root": "ok",
                "manifest": "ok",
                "sessions_db": "ok",
                "audit_db": "ok",
            },
        },
        "meta": {},
    }


def test_storage_readiness_reports_partial_schema_as_not_ready(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    settings.data_root.mkdir(parents=True, exist_ok=True)
    settings.meta_root.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(settings.sessions_db_path) as connection:
        connection.execute(
            """
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY,
                role TEXT NOT NULL
            )
            """
        )
        connection.commit()

    with sqlite3.connect(settings.audit_db_path) as connection:
        connection.execute(
            """
            CREATE TABLE audit_events (
                event_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE mutation_requests (
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                PRIMARY KEY (entity_type, entity_id, action, idempotency_key)
            )
            """
        )
        connection.commit()

    payload = build_storage_readiness_payload(settings)

    assert payload == {
        "status": "not_ready",
        "checks": {
            "data_root": "ok",
            "manifest": "missing",
            "sessions_db": "missing",
            "audit_db": "missing",
        },
    }


def test_storage_readiness_reports_invalid_primary_keys_as_not_ready(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    settings.data_root.mkdir(parents=True, exist_ok=True)
    settings.meta_root.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(settings.sessions_db_path) as connection:
        connection.execute(
            """
            CREATE TABLE sessions (
                session_id TEXT NOT NULL,
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
            """
        )
        connection.commit()

    with sqlite3.connect(settings.audit_db_path) as connection:
        connection.execute(
            """
            CREATE TABLE audit_events (
                event_id TEXT NOT NULL,
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
            """
        )
        connection.execute(
            """
            CREATE TABLE mutation_requests (
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                actor_id TEXT,
                request_fingerprint TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.commit()

    payload = build_storage_readiness_payload(settings)

    assert payload == {
        "status": "not_ready",
        "checks": {
            "data_root": "ok",
            "manifest": "missing",
            "sessions_db": "missing",
            "audit_db": "missing",
        },
    }


def test_storage_readiness_reports_corrupt_database_files_as_not_ready(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    settings.data_root.mkdir(parents=True, exist_ok=True)
    settings.meta_root.mkdir(parents=True, exist_ok=True)
    settings.sessions_db_path.write_text("not-a-sqlite-db", encoding="utf-8")
    settings.audit_db_path.write_text("not-a-sqlite-db", encoding="utf-8")

    payload = build_storage_readiness_payload(settings)

    assert payload == {
        "status": "not_ready",
        "checks": {
            "data_root": "ok",
            "manifest": "missing",
            "sessions_db": "missing",
            "audit_db": "missing",
        },
    }
