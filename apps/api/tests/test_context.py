import hashlib
import hmac
import shutil
import tempfile
import time
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
SIGNED_CONTEXT_SECRET = "test-context-secret-32-bytes-minimum"


def build_signed_settings(tmp_path: Path, **overrides) -> Settings:
    digest = hashlib.sha1(f"signed-{tmp_path}".encode("utf-8")).hexdigest()[:10]
    data_root = Path(tempfile.gettempdir()) / "kl" / digest
    shutil.rmtree(data_root, ignore_errors=True)
    return Settings(data_root=data_root, **overrides)


def build_signed_client(tmp_path: Path, **settings_overrides) -> tuple[TestClient, Settings]:
    settings = build_signed_settings(tmp_path, **settings_overrides)
    return TestClient(create_app(settings), raise_server_exceptions=False), settings


def signed_context_headers(
    *,
    role: str = "student",
    actor_id: str = "stu-kim-minji",
    course_id: str = "course-calculus-1",
    class_id: str = "class-calculus-1-2026-spring-a",
    domain: str = "academic",
    method: str = "GET",
    path: str = "/api/v1/context/self",
    timestamp: str | None = None,
) -> dict[str, str]:
    resolved_timestamp = timestamp or str(int(time.time()))
    payload = "\n".join(
        [
            "knowloop-context-v1",
            method.upper(),
            path,
            resolved_timestamp,
            "x-knowloop-profile-id:",
            f"x-knowloop-role:{role}",
            f"x-knowloop-actor-id:{actor_id}",
            f"x-knowloop-course-id:{course_id}",
            f"x-knowloop-class-id:{class_id}",
            f"x-knowloop-domain:{domain}",
        ]
    )
    signature = hmac.new(
        SIGNED_CONTEXT_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-Knowloop-Role": role,
        "X-Knowloop-Actor-Id": actor_id,
        "X-Knowloop-Course-Id": course_id,
        "X-Knowloop-Class-Id": class_id,
        "X-Knowloop-Domain": domain,
        "X-Knowloop-Context-Timestamp": resolved_timestamp,
        "X-Knowloop-Context-Signature": f"v1={signature}",
    }


def test_signed_context_mode_rejects_unsigned_context_headers(tmp_path: Path) -> None:
    client, _settings = build_signed_client(
        tmp_path,
        context_trust_mode="signed",
        trusted_context_secret=SIGNED_CONTEXT_SECRET,
    )

    response = client.get(
        "/api/v1/context/self",
        headers={
            "X-Knowloop-Role": "student",
            "X-Knowloop-Actor-Id": "stu-kim-minji",
            "X-Knowloop-Course-Id": "course-calculus-1",
            "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
            "X-Knowloop-Domain": "academic",
        },
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "untrusted_context"
    assert payload["error"]["details"] == {
        "missing_headers": [
            "X-Knowloop-Context-Timestamp",
            "X-Knowloop-Context-Signature",
        ]
    }


def test_signed_context_mode_accepts_signed_context_headers(tmp_path: Path) -> None:
    client, _settings = build_signed_client(
        tmp_path,
        context_trust_mode="signed",
        trusted_context_secret=SIGNED_CONTEXT_SECRET,
    )

    response = client.get(
        "/api/v1/context/self",
        headers=signed_context_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["context_source"] == "signed_headers"
    assert payload["data"]["role"] == "student"
    assert payload["data"]["actor_id"] == "stu-kim-minji"
    assert payload["data"]["domain"] == "academic"


def test_signed_context_mode_rejects_tampered_context_headers(tmp_path: Path) -> None:
    client, _settings = build_signed_client(
        tmp_path,
        context_trust_mode="signed",
        trusted_context_secret=SIGNED_CONTEXT_SECRET,
    )
    headers = signed_context_headers()
    headers["X-Knowloop-Role"] = "instructor"

    response = client.get("/api/v1/context/self", headers=headers)

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "untrusted_context"
    assert payload["error"]["details"] == {"adapter": "signed_headers"}


def test_signed_context_mode_rejects_stale_context_signature(tmp_path: Path) -> None:
    client, _settings = build_signed_client(
        tmp_path,
        context_trust_mode="signed",
        trusted_context_secret=SIGNED_CONTEXT_SECRET,
        trusted_context_max_age_seconds=30,
    )

    response = client.get(
        "/api/v1/context/self",
        headers=signed_context_headers(timestamp=str(int(time.time()) - 120)),
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "untrusted_context"
    assert payload["error"]["details"] == {"max_age_seconds": 30}


def test_signed_context_mode_rejects_far_future_context_signature(tmp_path: Path) -> None:
    client, _settings = build_signed_client(
        tmp_path,
        context_trust_mode="signed",
        trusted_context_secret=SIGNED_CONTEXT_SECRET,
    )

    response = client.get(
        "/api/v1/context/self",
        headers=signed_context_headers(timestamp=str(int(time.time()) + 120)),
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "untrusted_context"
    assert payload["error"]["details"] == {"max_future_skew_seconds": 30}


def test_signed_context_mode_rejects_path_mismatch(tmp_path: Path) -> None:
    client, _settings = build_signed_client(
        tmp_path,
        context_trust_mode="signed",
        trusted_context_secret=SIGNED_CONTEXT_SECRET,
    )

    response = client.get(
        "/api/v1/context/self",
        headers=signed_context_headers(path="/api/v1/sources"),
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "untrusted_context"
    assert payload["error"]["details"] == {"adapter": "signed_headers"}


def test_signed_context_mode_accepts_signed_profile_headers_in_demo_mode(
    tmp_path: Path,
) -> None:
    timestamp = str(int(time.time()))
    payload = "\n".join(
        [
            "knowloop-context-v1",
            "GET",
            "/api/v1/context/self",
            timestamp,
            "x-knowloop-profile-id:student-minji",
            "x-knowloop-role:",
            "x-knowloop-actor-id:",
            "x-knowloop-course-id:",
            "x-knowloop-class-id:",
            "x-knowloop-domain:",
        ]
    )
    signature = hmac.new(
        SIGNED_CONTEXT_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    client, _settings = build_signed_client(
        tmp_path,
        context_trust_mode="signed",
        trusted_context_secret=SIGNED_CONTEXT_SECRET,
    )

    response = client.get(
        "/api/v1/context/self",
        headers={
            "X-Knowloop-Profile-Id": "student-minji",
            "X-Knowloop-Context-Timestamp": timestamp,
            "X-Knowloop-Context-Signature": f"v1={signature}",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["context_source"] == "profile"
    assert payload["data"]["profile_id"] == "student-minji"


def test_signed_context_mode_blocks_demo_profile_registry(tmp_path: Path) -> None:
    client, _settings = build_signed_client(
        tmp_path,
        context_trust_mode="signed",
        trusted_context_secret=SIGNED_CONTEXT_SECRET,
        demo_context_profiles_enabled=False,
    )

    response = client.get("/api/v1/context/profiles")

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "demo_profiles_disabled"


def test_profile_header_is_rejected_when_demo_profiles_are_disabled(tmp_path: Path) -> None:
    client, _settings = build_signed_client(
        tmp_path,
        demo_context_profiles_enabled=False,
    )

    response = client.get(
        "/api/v1/context/self",
        headers={"X-Knowloop-Profile-Id": "student-minji"},
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "demo_profiles_disabled"


def test_production_settings_require_signed_context_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="context_trust_mode"):
        build_signed_settings(tmp_path, app_env="production")


def test_signed_context_mode_rejects_weak_secret(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="trusted_context_secret"):
        build_signed_settings(
            tmp_path,
            context_trust_mode="signed",
            trusted_context_secret="short",
        )


def test_production_settings_accept_signed_context_defaults(tmp_path: Path) -> None:
    settings = build_signed_settings(
        tmp_path,
        app_env="production",
        context_trust_mode="signed",
        trusted_context_secret=SIGNED_CONTEXT_SECRET,
    )

    assert settings.demo_context_profiles_enabled is False


def test_production_settings_reject_demo_profile_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="demo_context_profiles_enabled"):
        build_signed_settings(
            tmp_path,
            app_env="production",
            context_trust_mode="signed",
            trusted_context_secret=SIGNED_CONTEXT_SECRET,
            demo_context_profiles_enabled=True,
        )
