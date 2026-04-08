import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from knowloop_api.core.config import Settings
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
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()

    return {row[0] for row in rows}


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

    assert settings.sessions_db_path.exists()
    assert settings.audit_db_path.exists()
    assert {"sessions"}.issubset(read_table_names(settings.sessions_db_path))
    assert {"audit_events"}.issubset(read_table_names(settings.audit_db_path))


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
                "sessions_db": "ok",
                "audit_db": "ok",
            },
        },
        "meta": {},
    }
