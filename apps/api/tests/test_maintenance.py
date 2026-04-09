import hashlib
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole, SourceType
from knowloop_api.core.frontmatter import parse_frontmatter_document
from knowloop_api.db.bootstrap import bootstrap_storage
from knowloop_api.main import create_app
from knowloop_api.services.candidates import CandidateItem, create_candidate
from knowloop_api.services.sources import SourceRegistrationInput, register_source

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "data" / "fixtures"


def build_settings(tmp_path: Path) -> Settings:
    digest = hashlib.sha1(str(tmp_path).encode("utf-8")).hexdigest()[:10]
    data_root = Path(tempfile.gettempdir()) / "kl" / digest
    shutil.rmtree(data_root, ignore_errors=True)
    return Settings(data_root=data_root)


def build_client(tmp_path: Path) -> tuple[TestClient, Settings]:
    settings = build_settings(tmp_path)
    return TestClient(create_app(settings), raise_server_exceptions=False), settings


def build_headers(
    *,
    role: str,
    actor_id: str,
    course_id: str = "course-calculus-1",
    class_id: str = "class-calculus-1-2026-spring-a",
    request_id: str = "req-test-maintenance",
    domain: str | None = None,
) -> dict[str, str]:
    headers = {
        "X-Knowloop-Role": role,
        "X-Knowloop-Actor-Id": actor_id,
        "X-Knowloop-Course-Id": course_id,
        "X-Knowloop-Class-Id": class_id,
        "X-Request-Id": request_id,
    }
    if domain is not None:
        headers["X-Knowloop-Domain"] = domain
    return headers


def seed_maintenance_runtime(settings: Settings) -> None:
    bootstrap_storage(settings)
    source_contents = (FIXTURE_ROOT / "sources" / "lecture-note-week-03-chain-rule.md").read_text(
        encoding="utf-8"
    )
    metadata, body = parse_frontmatter_document(source_contents)
    register_source(
        settings,
        SourceRegistrationInput(
            source_type=SourceType(str(metadata["source_type"])),
            title=str(metadata["title"]),
            content=body,
            mime_type="text/markdown",
            filename="lecture-note-week-03-chain-rule.md",
        ),
        course_id=str(metadata["course_id"]),
        class_id=str(metadata["class_id"]),
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        created_at=datetime.fromisoformat(str(metadata["created_at"]).replace("Z", "+00:00")),
    )

    stale_candidate = CandidateItem.model_validate(
        {
            "candidate_id": (
                "cand-misconception-class-calculus-1-2026-spring-a-"
                "old-signal-20260301T090000Z"
            ),
            "kind": "misconception",
            "status": "open",
            "title": "Old unresolved chain rule misconception",
            "summary": "This candidate has been waiting long enough to count as stale.",
            "class_id": "class-calculus-1-2026-spring-a",
            "course_id": "course-calculus-1",
            "actor_role": "system",
            "confidence": 0.72,
            "tags": ["chain-rule", "stale"],
            "source_refs": [
                {
                    "source_id": (
                        "src-lecture-note-class-calculus-1-2026-spring-a-"
                        "week-03-20260408T103000Z"
                    ),
                    "source_type": "lecture_note",
                }
            ],
            "session_refs": [],
            "created_at": "2026-03-01T09:00:00Z",
        }
    )
    create_candidate(
        settings,
        stale_candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        request_id="req-seed-maintenance-candidate",
    )

    wiki_path = settings.data_root / "wiki" / "faq" / "maintenance-drift.md"
    wiki_path.parent.mkdir(parents=True, exist_ok=True)
    wiki_path.write_text(
        """---
page_id: page-faq-maintenance-drift
domain: faq
title: Maintenance Drift Example
course_id: course-calculus-1
class_scope: class-calculus-1-2026-spring-a
updated_at: 2026-04-08T10:40:00Z
source_refs: ["src-missing-maintenance-source"]
candidate_refs: ["cand-missing-maintenance-candidate"]
summary: A wiki page used to verify orphan maintenance checks.
---

# Maintenance Drift Example

This page intentionally references missing candidate and source records.
""",
        encoding="utf-8",
    )


def test_maintenance_report_detects_stale_candidates_and_orphan_refs(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["course_id"] == "course-calculus-1"
    assert payload["class_id"] == "class-calculus-1-2026-spring-a"
    assert payload["status"] == "error"
    assert payload["review_queue_count"] == 3
    assert payload["summary"] == {
        "errors": 2,
        "warnings": 1,
        "stale_candidates": 1,
        "orphan_candidate_refs": 1,
        "orphan_source_refs": 1,
    }
    assert {check["code"] for check in payload["checks"]} == {
        "stale_candidate",
        "orphan_wiki_candidate_ref",
        "orphan_wiki_source_ref",
    }
    assert (
        settings.meta_root
        / "maintenance"
        / "course-calculus-1"
        / "class-calculus-1-2026-spring-a"
        / "lint-status.json"
    ).exists()


def test_maintenance_status_returns_latest_report_to_instructor(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-prime",
            domain="review",
        ),
    )
    response = client.get(
        "/api/v1/maintenance/status",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-maintenance-status",
            domain="academic",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["course_id"] == "course-calculus-1"
    assert payload["class_id"] == "class-calculus-1-2026-spring-a"
    assert payload["status"] == "error"
    assert payload["last_run_at"] is not None
    assert payload["health_score"] < 100


def test_maintenance_status_returns_not_run_without_creating_report(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    response = client.get(
        "/api/v1/maintenance/status",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-maintenance-status-not-run",
            domain="academic",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["course_id"] == "course-calculus-1"
    assert payload["class_id"] == "class-calculus-1-2026-spring-a"
    assert payload["status"] == "not-run"
    assert payload["last_run_at"] is None
    assert payload["checks"] == []
    assert not (
        settings.meta_root
        / "maintenance"
        / "course-calculus-1"
        / "class-calculus-1-2026-spring-a"
        / "lint-status.json"
    ).exists()


def test_maintenance_status_is_scoped_per_course_and_class(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    report_response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-primary-scope",
            domain="review",
        ),
    )
    assert report_response.status_code == 200

    other_scope_response = client.get(
        "/api/v1/maintenance/status",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-maintenance-status-other-scope",
            course_id="course-calculus-1",
            class_id="class-calculus-1-2026-spring-b",
            domain="academic",
        ),
    )

    assert other_scope_response.status_code == 200
    payload = other_scope_response.json()["data"]
    assert payload["course_id"] == "course-calculus-1"
    assert payload["class_id"] == "class-calculus-1-2026-spring-b"
    assert payload["status"] == "not-run"
    assert payload["checks"] == []


def test_maintenance_report_rejects_instructor_role(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-maintenance-report-instructor-denied",
            domain="academic",
        ),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_scope"


def test_maintenance_routes_reject_operator_role(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    response = client.get(
        "/api/v1/maintenance/status",
        headers=build_headers(
            role="operator",
            actor_id="ops-academic-office",
            request_id="req-maintenance-operator-denied",
            domain="operations",
        ),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_scope"
