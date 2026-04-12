import hashlib
import shutil
import sqlite3
import tempfile
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient

from knowloop_api.core.config import Settings
from knowloop_api.db.bootstrap import bootstrap_storage, build_storage_readiness_payload
from knowloop_api.main import create_app


def build_settings(tmp_path: Path) -> Settings:
    digest = hashlib.sha1(str(tmp_path).encode("utf-8")).hexdigest()[:10]
    data_root = Path(tempfile.gettempdir()) / "kl" / digest
    shutil.rmtree(data_root, ignore_errors=True)
    return Settings(
        data_root=data_root,
    )


def build_client(tmp_path: Path) -> tuple[TestClient, Settings]:
    settings = build_settings(tmp_path)
    return TestClient(create_app(settings)), settings


def assert_server_owned_request_id(
    response,
    *,
    client_request_id: str | None = None,
) -> str:
    payload = response.json()
    request_id = payload["request_id"]
    assert isinstance(request_id, str)
    assert request_id.strip()
    assert response.headers["X-Request-Id"] == request_id
    if client_request_id is not None:
        assert request_id != client_request_id
        assert response.headers["X-Client-Request-Id"] == client_request_id
    else:
        assert "X-Client-Request-Id" not in response.headers
    return request_id


def assert_api_success_envelope(
    response,
    *,
    expected_data: object,
    client_request_id: str | None = None,
) -> tuple[str, dict[str, object]]:
    request_id = assert_server_owned_request_id(
        response,
        client_request_id=client_request_id,
    )
    payload = response.json()
    assert set(payload.keys()) == {"request_id", "data", "meta"}
    assert payload["data"] == expected_data
    assert isinstance(payload["meta"], dict)
    return request_id, payload["meta"]


def assert_api_error_envelope(
    response,
    *,
    expected_code: str | None = None,
    expected_message: str | None = None,
    expected_details: dict[str, object] | None = None,
    client_request_id: str | None = None,
) -> str:
    request_id = assert_server_owned_request_id(
        response,
        client_request_id=client_request_id,
    )
    payload = response.json()
    assert set(payload.keys()) == {"request_id", "error"}
    assert "detail" not in payload
    assert set(payload["error"].keys()) == {"code", "message", "details"}
    assert isinstance(payload["error"]["code"], str)
    assert payload["error"]["code"].strip()
    if expected_code is not None:
        assert payload["error"]["code"] == expected_code
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"].strip()
    assert isinstance(payload["error"]["details"], dict)
    if expected_message is not None:
        assert payload["error"]["message"] == expected_message
    if expected_details is not None:
        assert payload["error"]["details"] == expected_details
    return request_id


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

    response = client.get(
        "/api/v1/system/health",
        headers={"X-Request-Id": "req-client-supplied-api-health"},
    )

    assert response.status_code == 200
    assert_api_success_envelope(
        response,
        expected_data={"status": "ok"},
        client_request_id="req-client-supplied-api-health",
    )


def test_api_health_endpoint_uses_attempt_local_request_ids(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    first_response = client.get(
        "/api/v1/system/health",
        headers={"X-Request-Id": "req-client-supplied-api-health-replay"},
    )
    second_response = client.get(
        "/api/v1/system/health",
        headers={"X-Request-Id": "req-client-supplied-api-health-replay"},
    )

    first_request_id = assert_server_owned_request_id(
        first_response,
        client_request_id="req-client-supplied-api-health-replay",
    )
    second_request_id = assert_server_owned_request_id(
        second_response,
        client_request_id="req-client-supplied-api-health-replay",
    )

    assert first_request_id != second_request_id


def test_api_health_endpoint_emits_request_id_without_client_header(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get("/api/v1/system/health")

    assert response.status_code == 200
    assert_api_success_envelope(
        response,
        expected_data={"status": "ok"},
    )


def test_api_health_endpoint_drops_invalid_client_request_id_for_correlation(
    tmp_path: Path,
) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get(
        "/api/v1/system/health",
        headers={"X-Request-Id": "invalid request id"},
    )

    assert response.status_code == 200
    assert_api_success_envelope(
        response,
        expected_data={"status": "ok"},
    )


def test_api_health_endpoint_drops_client_request_id_with_surrounding_whitespace(
    tmp_path: Path,
) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get(
        "/api/v1/system/health",
        headers={"X-Request-Id": " req-client-with-padding "},
    )

    assert response.status_code == 200
    assert_api_success_envelope(
        response,
        expected_data={"status": "ok"},
    )


def test_api_health_endpoint_drops_comma_joined_client_request_id_for_correlation(
    tmp_path: Path,
) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get(
        "/api/v1/system/health",
        headers={"X-Request-Id": "req-client-one,req-client-two"},
    )

    assert response.status_code == 200
    assert_api_success_envelope(
        response,
        expected_data={"status": "ok"},
    )


def test_api_health_endpoint_drops_oversized_client_request_id_for_correlation(
    tmp_path: Path,
) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get(
        "/api/v1/system/health",
        headers={"X-Request-Id": "a" * 129},
    )

    assert response.status_code == 200
    assert_api_success_envelope(
        response,
        expected_data={"status": "ok"},
    )


def test_non_system_api_routes_replace_client_request_ids_on_boundary_errors(
    tmp_path: Path,
) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get(
        "/api/v1/sources",
        headers={"X-Request-Id": "req-client-supplied-sources-missing-context"},
    )

    assert response.status_code == 422
    assert_api_error_envelope(
        response,
        expected_code="missing_context",
        client_request_id="req-client-supplied-sources-missing-context",
    )


def test_non_system_api_success_routes_emit_server_owned_request_ids(
    tmp_path: Path,
) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get(
        "/api/v1/sources",
        headers={
            "X-Knowloop-Role": "instructor",
            "X-Knowloop-Actor-Id": "ins-calculus-team",
            "X-Knowloop-Course-Id": "course-calculus-1",
            "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
            "X-Knowloop-Domain": "academic",
            "X-Request-Id": "req-client-supplied-sources-success",
        },
    )

    assert response.status_code == 200
    request_id = assert_server_owned_request_id(
        response,
        client_request_id="req-client-supplied-sources-success",
    )
    payload = response.json()
    assert set(payload.keys()) == {"request_id", "data", "meta"}
    assert payload["request_id"] == request_id
    assert isinstance(payload["data"], list)
    assert isinstance(payload["meta"], dict)


def test_api_framework_404_emits_request_id_without_client_header(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get("/api/v1/system/unknown")

    assert response.status_code == 404
    assert_api_error_envelope(
        response,
        expected_code="not_found",
        expected_details={},
    )


def test_api_framework_validation_422_uses_standard_envelope(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    app = create_app(settings)

    @app.get("/api/v1/test-validation")
    def test_validation_route(limit: int) -> dict[str, int]:
        return {"limit": limit}

    client = TestClient(app)

    response = client.get(
        "/api/v1/test-validation?limit=oops",
        headers={
            "X-Knowloop-Role": "instructor",
            "X-Knowloop-Actor-Id": "ins-calculus-team",
            "X-Knowloop-Course-Id": "course-calculus-1",
            "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
            "X-Knowloop-Domain": "academic",
            "X-Request-Id": "req-client-supplied-api-422",
        },
    )

    assert response.status_code == 422
    assert_api_error_envelope(
        response,
        expected_code="validation_failed",
        client_request_id="req-client-supplied-api-422",
    )


def test_api_framework_validation_422_drops_invalid_client_request_id_for_correlation(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    app = create_app(settings)

    @app.get("/api/v1/test-validation-invalid-client-id")
    def test_validation_invalid_client_id_route(limit: int) -> dict[str, int]:
        return {"limit": limit}

    client = TestClient(app)

    response = client.get(
        "/api/v1/test-validation-invalid-client-id?limit=oops",
        headers={
            "X-Knowloop-Role": "instructor",
            "X-Knowloop-Actor-Id": "ins-calculus-team",
            "X-Knowloop-Course-Id": "course-calculus-1",
            "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
            "X-Knowloop-Domain": "academic",
            "X-Request-Id": "invalid request id",
        },
    )

    assert response.status_code == 422
    assert_api_error_envelope(
        response,
        expected_code="validation_failed",
    )


def test_api_framework_404_drops_invalid_client_request_id_for_correlation(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get(
        "/api/v1/system/unknown",
        headers={"X-Request-Id": "invalid request id"},
    )

    assert response.status_code == 404
    assert_api_error_envelope(
        response,
        expected_code="not_found",
    )


def test_api_http_exception_sanitizes_reserved_request_headers(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    app = create_app(settings)

    @app.get("/api/v1/test-http-exception")
    def test_http_exception_route() -> None:
        raise HTTPException(
            status_code=429,
            detail="busy",
            headers={
                "X-Request-Id": "downstream-request-id",
                "X-Client-Request-Id": "downstream-client-request-id",
                "Retry-After": "7",
            },
        )

    client = TestClient(app)
    response = client.get(
        "/api/v1/test-http-exception",
        headers={"X-Request-Id": "req-client-http-exception"},
    )

    assert response.status_code == 429
    assert_server_owned_request_id(
        response,
        client_request_id="req-client-http-exception",
    )
    payload = response.json()
    assert "detail" not in payload
    assert payload["error"] == {
        "code": "http_429",
        "message": "Request could not be completed.",
        "details": {},
    }
    assert response.headers["Retry-After"] == "7"


def test_api_http_exception_uses_fallback_error_mapping_for_dict_detail(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    app = create_app(settings)

    @app.get("/api/v1/test-http-exception-dict-detail")
    def test_http_exception_dict_detail_route() -> None:
        raise HTTPException(
            status_code=405,
            detail={
                "code": "custom_not_allowed",
                "message": "Custom message should not leak.",
            },
        )

    client = TestClient(app)
    response = client.get(
        "/api/v1/test-http-exception-dict-detail",
        headers={"X-Request-Id": "req-client-http-exception-dict"},
    )

    assert response.status_code == 405
    assert_api_error_envelope(
        response,
        expected_code="invalid_request",
        expected_message="Method is not allowed for this route.",
        expected_details={},
        client_request_id="req-client-http-exception-dict",
    )


def test_api_http_exception_403_uses_forbidden_scope_fallback(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    app = create_app(settings)

    @app.get("/api/v1/test-http-exception-forbidden")
    def test_http_exception_forbidden_route() -> None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "custom_forbidden",
                "message": "Custom forbidden message should not leak.",
            },
        )

    client = TestClient(app)
    response = client.get(
        "/api/v1/test-http-exception-forbidden",
        headers={"X-Request-Id": "req-client-http-exception-forbidden"},
    )

    assert response.status_code == 403
    assert_api_error_envelope(
        response,
        expected_code="forbidden_scope",
        expected_message="Request could not access this API scope.",
        expected_details={},
        client_request_id="req-client-http-exception-forbidden",
    )


def test_api_http_exception_drops_invalid_client_request_id_for_correlation(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    app = create_app(settings)

    @app.get("/api/v1/test-http-exception-invalid-client-id")
    def test_http_exception_invalid_client_id_route() -> None:
        raise HTTPException(status_code=429, detail="busy")

    client = TestClient(app)
    response = client.get(
        "/api/v1/test-http-exception-invalid-client-id",
        headers={"X-Request-Id": "invalid request id"},
    )

    assert response.status_code == 429
    assert_api_error_envelope(
        response,
        expected_code="http_429",
        expected_message="Request could not be completed.",
        expected_details={},
    )


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
        "replay_intent_json",
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
    api_response = client.get(
        "/api/v1/system/ready",
        headers={"X-Request-Id": "req-client-supplied-api-ready"},
    )

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
    assert_api_success_envelope(
        api_response,
        expected_data={
            "status": "ready",
            "checks": {
                "data_root": "ok",
                "manifest": "ok",
                "sessions_db": "ok",
                "audit_db": "ok",
            },
        },
        client_request_id="req-client-supplied-api-ready",
    )


def test_api_routes_wrap_framework_404_and_405_errors_in_standard_envelope(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    not_found_response = client.get(
        "/api/v1/system/unknown",
        headers={"X-Request-Id": "req-client-supplied-api-404"},
    )
    method_not_allowed_response = client.post(
        "/api/v1/system/health",
        headers={"X-Request-Id": "req-client-supplied-api-405"},
    )

    assert not_found_response.status_code == 404
    not_found_request_id = assert_api_error_envelope(
        not_found_response,
        expected_code="not_found",
        expected_details={},
        client_request_id="req-client-supplied-api-404",
    )
    assert method_not_allowed_response.status_code == 405
    method_not_allowed_request_id = assert_api_error_envelope(
        method_not_allowed_response,
        expected_code="invalid_request",
        expected_details={},
        client_request_id="req-client-supplied-api-405",
    )
    assert not_found_request_id != method_not_allowed_request_id


def test_api_framework_405_drops_invalid_client_request_id_for_correlation(
    tmp_path: Path,
) -> None:
    client, _settings = build_client(tmp_path)

    response = client.post(
        "/api/v1/system/health",
        headers={"X-Request-Id": "invalid request id"},
    )

    assert response.status_code == 405
    assert_api_error_envelope(
        response,
        expected_code="invalid_request",
        expected_message="Method is not allowed for this route.",
        expected_details={},
    )


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
                learning_note_refs_json TEXT NOT NULL DEFAULT '[]',
                replay_intent_snapshot TEXT
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
