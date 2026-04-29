from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole
from knowloop_api.main import create_app
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
    request_id: str = "req-test-learning",
    domain: str = "academic",
) -> dict[str, str]:
    return {
        "X-Knowloop-Role": role,
        "X-Knowloop-Actor-Id": actor_id,
        "X-Knowloop-Course-Id": course_id,
        "X-Knowloop-Class-Id": class_id,
        "X-Knowloop-Domain": domain,
        "X-Request-Id": request_id,
    }


def load_json_fixture(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def seed_learning_note_fixture(settings: Settings) -> LearningNote:
    payload = load_json_fixture(
        FIXTURE_ROOT / "learning" / "student-minji-learning-note.json"
    )
    assert isinstance(payload, dict)
    note = LearningNote.model_validate(payload).model_copy(
        update={"actor_role": ActorRole.STUDENT}
    )
    return upsert_learning_note(
        settings,
        note,
        actor_id="stu-kim-minji",
        request_id="req-seed-learning-note",
    )


def seed_session_history(settings: Settings) -> None:
    payload = load_json_fixture(FIXTURE_ROOT / "sessions" / "student-minji-history.json")
    assert isinstance(payload, list)
    for item in payload:
        save_session(
            settings,
            SessionRecord.model_validate(item),
            request_id="req-seed-learning-session",
        )


def seed_wiki_pack(settings: Settings) -> None:
    _seed_wiki_fixture(
        settings,
        fixture_name="concepts-chain-rule.seed.md",
        target_relative_path="wiki/concepts/class-calculus-1-2026-spring-a/chain-rule.md",
    )
    _seed_wiki_fixture(
        settings,
        fixture_name="faq-homework-submission.after.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )
    _seed_wiki_fixture(
        settings,
        fixture_name="misconception-chain-rule.after.md",
        target_relative_path="wiki/misconceptions/class-calculus-1-2026-spring-a/chain-rule-product-rule.md",
    )


def _seed_wiki_fixture(
    settings: Settings,
    *,
    fixture_name: str,
    target_relative_path: str,
) -> None:
    target_path = settings.data_root / Path(target_relative_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        (FIXTURE_ROOT / "wiki" / fixture_name).read_text(encoding="utf-8-sig"),
        encoding="utf-8",
    )


def test_student_learning_self_returns_structured_console_snapshot(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_learning_note_fixture(settings)
    seed_wiki_pack(settings)
    seed_session_history(settings)

    response = client.get(
        "/api/v1/learning/self",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-student-learning-self",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"]
    assert payload["meta"] == {}

    data = payload["data"]
    assert set(data) == {
        "summary",
        "learning_note",
        "confusion_signals",
        "learning_notes",
        "gaps",
        "next_actions",
        "related_wiki",
        "recent_sessions",
    }

    assert data["summary"] == {
        "concept_count": 3,
        "confusion_signal_count": 2,
        "gap_count": 2,
        "next_action_count": 2,
        "session_ref_count": 2,
        "source_ref_count": 2,
        "related_wiki_count": 3,
        "updated_at": "2026-04-08T11:42:00Z",
    }

    learning_note = data["learning_note"]
    assert learning_note["learning_note_id"] == (
        "learn-stu-kim-minji-calculus-1-calculus-1-2026-spring-a"
    )
    assert learning_note["student_id"] == "stu-kim-minji"
    assert learning_note["course_id"] == "course-calculus-1"
    assert learning_note["class_id"] == "class-calculus-1-2026-spring-a"
    assert learning_note["concepts"] == ["chain rule", "product rule", "composition"]
    assert len(learning_note["session_refs"]) == 2

    assert len(data["confusion_signals"]) == 2
    assert data["confusion_signals"][0]["linked_session_id"] == (
        "ses-student-stu-kim-minji-class-calculus-1-2026-spring-a-20260407T133000Z"
    )

    assert len(data["learning_notes"]) == 1
    assert data["learning_notes"][0]["note_id"] == learning_note["learning_note_id"]
    assert data["learning_notes"][0]["linked_session_title"]

    assert len(data["gaps"]) == 2
    assert len(data["next_actions"]) == 2

    related_page_ids = {item["page_id"] for item in data["related_wiki"]}
    assert related_page_ids == {
        "page-concepts-chain-rule",
        "page-faq-homework-submission",
        "page-misconceptions-chain-rule-product-rule",
    }

    recent_sessions = data["recent_sessions"]
    assert [item["session_id"] for item in recent_sessions] == [
        "ses-student-stu-kim-minji-class-calculus-1-2026-spring-a-20260407T133000Z",
        "ses-student-stu-kim-minji-class-calculus-1-2026-spring-a-20260408T114000Z",
    ]
    assert all(item["preview"] for item in recent_sessions)


def test_student_learning_self_returns_empty_console_when_note_missing(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_session_history(settings)

    response = client.get(
        "/api/v1/learning/self",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-student-learning-self-empty",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    assert data["summary"] == {
        "concept_count": 0,
        "confusion_signal_count": 0,
        "gap_count": 0,
        "next_action_count": 0,
        "session_ref_count": 0,
        "source_ref_count": 0,
        "related_wiki_count": 0,
        "updated_at": None,
    }
    assert data["learning_note"] is None
    assert data["confusion_signals"] == []
    assert data["learning_notes"] == []
    assert data["gaps"] == []
    assert data["next_actions"] == []
    assert data["related_wiki"] == []
    assert data["recent_sessions"] == []


def test_learning_self_forbids_non_student_roles(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_learning_note_fixture(settings)

    response = client.get(
        "/api/v1/learning/self",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-instructor-learning-self",
        ),
    )

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "forbidden_scope"
    assert "personal learning console" in body["error"]["message"]
