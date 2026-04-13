import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole
from knowloop_api.db.bootstrap import bootstrap_storage
from knowloop_api.main import create_app
from knowloop_api.services.candidates import CandidateItem, create_candidate
from knowloop_api.services.learning import LearningNote, upsert_learning_note
from knowloop_api.services.sessions import SessionRecord, save_session

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
    request_id: str = "req-test-instructor",
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


def load_session_fixture(filename: str) -> list[SessionRecord]:
    payload = json.loads((FIXTURE_ROOT / "sessions" / filename).read_text(encoding="utf-8"))
    return [SessionRecord.model_validate(item) for item in payload]


def load_candidate_fixture(filename: str) -> CandidateItem:
    payload = json.loads((FIXTURE_ROOT / "candidates" / filename).read_text(encoding="utf-8"))
    return CandidateItem.model_validate(payload)


def seed_instructor_runtime(settings: Settings) -> None:
    bootstrap_storage(settings)
    for filename in (
        "student-minji-history.json",
        "student-jiyoon-history.json",
        "student-doyun-history.json",
    ):
        for session in load_session_fixture(filename):
            save_session(settings, session, request_id="req-seed-instructor-session")

    for filename in (
        "open-misconception-chain-rule.json",
        "open-misconception-chain-rule-duplicate.json",
        "open-faq-homework-deadline.json",
        "open-unresolved-integral.json",
        "open-operations-refund.json",
    ):
        create_candidate(
            settings,
            load_candidate_fixture(filename),
            actor_role=ActorRole.SYSTEM,
            actor_id="system-seed",
            request_id="req-seed-instructor-candidate",
        )

    for note in (
        LearningNote(
            learning_note_id="learn-stu-kim-minji-calculus-1-calculus-1-2026-spring-a",
            student_id="stu-kim-minji",
            course_id="course-calculus-1",
            class_id="class-calculus-1-2026-spring-a",
            actor_role=ActorRole.SYSTEM,
            concepts=["chain rule", "substitution"],
            gaps=[
                "Differentiate the chain rule from the product rule.",
                "Recognize when substitution stops working.",
            ],
            next_actions=["Compare one chain-rule example with one product-rule example."],
            summary="Needs reinforcement on rule selection and substitution boundaries.",
            created_at=datetime(2026, 4, 8, 11, 10, tzinfo=UTC),
        ),
        LearningNote(
            learning_note_id="learn-stu-lee-doyun-calculus-1-calculus-1-2026-spring-a",
            student_id="stu-lee-doyun",
            course_id="course-calculus-1",
            class_id="class-calculus-1-2026-spring-a",
            actor_role=ActorRole.SYSTEM,
            concepts=["homework policy", "chain rule"],
            gaps=["Differentiate the chain rule from the product rule."],
            next_actions=["Review the misconception wiki before the next quiz."],
            summary="Mostly aligned, but still needs the rule-selection distinction.",
            created_at=datetime(2026, 4, 8, 11, 20, tzinfo=UTC),
        ),
    ):
        upsert_learning_note(
            settings,
            note,
            actor_id="system-seed",
            request_id="req-seed-instructor-learning",
        )


@pytest.mark.smoke
def test_instructor_overview_endpoint_returns_aggregated_academic_metrics(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_instructor_runtime(settings)

    response = client.get(
        "/api/v1/instructor/insights/overview",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-instructor-overview",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["student_session_count"] == 4
    assert payload["unique_student_count"] == 3
    assert payload["open_candidate_total"] == 4
    assert payload["candidate_counts"] == {
        "faq": 1,
        "misconception": 2,
        "unresolved_question": 1,
    }
    assert payload["students_with_learning_notes"] == 2
    assert payload["students_with_open_gaps"] == 2
    assert payload["top_topics"][0] == {
        "topic": "homework",
        "session_count": 2,
        "student_count": 2,
    }
    assert payload["top_gap_clusters"][0] == {
        "gap": "Differentiate the chain rule from the product rule.",
        "student_count": 2,
    }
    assert payload["top_patterns"][0]["kind"] == "misconception"
    assert payload["top_patterns"][0]["candidate_count"] == 2
    assert (
        payload["top_patterns"][0]["related_page_id"]
        == "page-misconceptions-chain-rule-product-rule"
    )
    assert "question" not in payload


def test_instructor_patterns_endpoint_groups_duplicate_candidates(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_instructor_runtime(settings)

    response = client.get(
        "/api/v1/instructor/insights/patterns",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-instructor-patterns",
            domain="academic",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 3
    first_pattern = payload["data"][0]
    assert (
        first_pattern["pattern_id"]
        == "ipat-misconception-page-misconceptions-chain-rule-product-rule"
    )
    assert first_pattern["candidate_count"] == 2
    assert first_pattern["student_count"] == 1
    assert first_pattern["session_count"] == 1
    assert first_pattern["candidate_ids"] == [
        "cand-misconception-class-calculus-1-2026-spring-a-chain-rule-duplicate-20260408T113800Z",
        "cand-misconception-class-calculus-1-2026-spring-a-chain-rule-product-rule-mixup-20260408T112000Z",
    ]


def test_instructor_patterns_endpoint_supports_kind_filter_and_pagination(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_instructor_runtime(settings)

    response = client.get(
        "/api/v1/instructor/insights/patterns?kind=faq&limit=1&offset=0",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-instructor-patterns-faq",
            domain="academic",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"] == {
        "kind": "faq",
        "limit": 1,
        "offset": 0,
        "total": 1,
    }
    assert payload["data"][0]["kind"] == "faq"
    assert payload["data"][0]["student_count"] == 2
    assert payload["data"][0]["session_count"] == 2


def test_instructor_insight_endpoints_reject_non_instructor_roles(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_instructor_runtime(settings)

    response = client.get(
        "/api/v1/instructor/insights/overview",
        headers=build_headers(
            role="operator",
            actor_id="ops-academic-office",
            request_id="req-operator-insight-denied",
            domain="operations",
        ),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_scope"
