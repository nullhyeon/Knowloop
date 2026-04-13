import hashlib
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowloop_api.core.config import Settings
from knowloop_api.main import create_app


def build_settings(tmp_path: Path) -> Settings:
    digest = hashlib.sha1(str(tmp_path).encode("utf-8")).hexdigest()[:10]
    data_root = Path(tempfile.gettempdir()) / "kl" / digest
    shutil.rmtree(data_root, ignore_errors=True)
    return Settings(data_root=data_root)


def build_client(tmp_path: Path) -> tuple[TestClient, Settings]:
    settings = build_settings(tmp_path)
    return TestClient(create_app(settings), raise_server_exceptions=False), settings


def test_context_profiles_endpoint_lists_demo_profiles(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get("/api/v1/context/profiles")

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] >= 4
    assert {item["profile_id"] for item in payload["data"]}.issuperset(
        {
            "student-minji",
            "instructor-calculus-team",
            "operator-academic-office",
            "validator-course-admin",
        }
    )


@pytest.mark.smoke
def test_context_self_endpoint_resolves_profile_header(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get(
        "/api/v1/context/self",
        headers={"X-Knowloop-Profile-Id": "student-minji"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["context_source"] == "profile"
    assert payload["data"] == {
        "profile_id": "student-minji",
        "profile_label": "학생 샘플 · 민지",
        "role": "student",
        "actor_id": "stu-kim-minji",
        "course_id": "course-calculus-1",
        "class_id": "class-calculus-1-2026-spring-a",
        "domain": "academic",
        "domain_was_explicit": False,
    }


@pytest.mark.smoke
def test_profile_header_can_access_scoped_routes_without_verbose_context_headers(
    tmp_path: Path,
) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get(
        "/api/v1/sources",
        headers={"X-Knowloop-Profile-Id": "instructor-calculus-team"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["data"], list)
    assert payload["request_id"].startswith("req-")


def test_profile_header_conflict_with_explicit_headers_returns_validation_error(
    tmp_path: Path,
) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get(
        "/api/v1/context/self",
        headers={
            "X-Knowloop-Profile-Id": "student-minji",
            "X-Knowloop-Role": "instructor",
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_failed"
    assert payload["error"]["details"] == {
        "profile_id": "student-minji",
        "conflicting_fields": ["role"],
    }
