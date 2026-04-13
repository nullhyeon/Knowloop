import hashlib
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowloop_api.core.config import Settings
from knowloop_api.db.manifest import load_manifest
from knowloop_api.demo_seed import seed_demo_runtime
from knowloop_api.main import create_app
from knowloop_api.services.learning import get_learning_note


def build_settings(tmp_path: Path) -> Settings:
    digest = hashlib.sha1(str(tmp_path).encode("utf-8")).hexdigest()[:10]
    data_root = Path(tempfile.gettempdir()) / "kl-demo-seed" / digest
    shutil.rmtree(data_root, ignore_errors=True)
    return Settings(data_root=data_root)


def test_seed_demo_runtime_populates_deployment_ready_sample(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)

    summary = seed_demo_runtime(settings, allow_destructive_reset=True)

    assert summary.course_id == "course-calculus-1"
    assert summary.class_id == "class-calculus-1-2026-spring-a"
    assert summary.source_count == 4
    assert summary.wiki_page_count == 4
    assert summary.session_count == 6
    assert summary.learning_note_count == 2
    assert summary.candidate_count == 3
    assert summary.maintenance_status == "warning"

    manifest = load_manifest(settings)
    assert len(manifest.sources) == 4
    assert {
        source.source_id for source in manifest.sources
    } == {
        "src-lecture-note-class-calculus-1-2026-spring-a-week-03-20260408T103000Z",
        "src-announcement-acad-class-calculus-1-2026-spring-a-homework-01-4774b218-20260408T104500Z",
        "src-lecture-note-class-calculus-1-2026-spring-a-chain-rule-support-20260408T111500Z",
        "src-operations-note-class-calculus-1-2026-spring-a-refund-policy-20260408T090000Z",
    }

    learning_note = get_learning_note(
        settings,
        student_id="stu-kim-minji",
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
    )
    assert learning_note is not None
    assert "chain rule" in learning_note.concepts
    assert len(learning_note.gaps) == 2

    client = TestClient(create_app(settings), raise_server_exceptions=False)

    recent_response = client.get(
        "/api/v1/sessions/recent",
        headers={"X-Knowloop-Profile-Id": "student-minji"},
    )
    assert recent_response.status_code == 200
    recent_payload = recent_response.json()
    assert recent_payload["meta"]["total"] == 3
    assert recent_payload["data"][0]["question_preview"]

    wiki_response = client.get(
        "/api/v1/wiki/pages",
        headers={"X-Knowloop-Profile-Id": "student-minji"},
    )
    assert wiki_response.status_code == 200
    wiki_payload = wiki_response.json()
    assert wiki_payload["meta"]["total"] == 3
    assert {page["page_id"] for page in wiki_payload["data"]}.issuperset(
        {
            "page-concepts-chain-rule",
            "page-faq-homework-submission",
            "page-misconceptions-chain-rule-product-rule",
        }
    )

    review_response = client.get(
        "/api/v1/review/candidates",
        headers={"X-Knowloop-Profile-Id": "instructor-calculus-team"},
    )
    assert review_response.status_code == 200
    review_payload = review_response.json()
    assert review_payload["meta"]["total"] == 3

    overview_response = client.get(
        "/api/v1/instructor/insights/overview",
        headers={"X-Knowloop-Profile-Id": "instructor-calculus-team"},
    )
    assert overview_response.status_code == 200
    overview_payload = overview_response.json()["data"]
    assert overview_payload["student_session_count"] == 6
    assert overview_payload["unique_student_count"] == 3
    assert overview_payload["students_with_learning_notes"] == 2
    assert overview_payload["open_candidate_total"] == 3

    instructor_status_response = client.get(
        "/api/v1/maintenance/status",
        headers={"X-Knowloop-Profile-Id": "instructor-calculus-team"},
    )
    assert instructor_status_response.status_code == 200
    instructor_status_payload = instructor_status_response.json()["data"]
    assert instructor_status_payload["status"] == "warning"
    assert instructor_status_payload["checks"]
    assert "summary" in instructor_status_payload["checks"][0]
    assert "details" not in instructor_status_payload["checks"][0]

    validator_report_response = client.get(
        "/api/v1/maintenance/report",
        headers={"X-Knowloop-Profile-Id": "validator-course-admin"},
    )
    assert validator_report_response.status_code == 200
    validator_report_payload = validator_report_response.json()["data"]
    assert validator_report_payload["status"] == "warning"
    assert any(
        check["code"] == "stale_candidate"
        for check in validator_report_payload["checks"]
    )


def test_seed_demo_runtime_requires_explicit_reset_opt_in(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)

    with pytest.raises(RuntimeError, match="allow_destructive_reset=True"):
        seed_demo_runtime(settings)
