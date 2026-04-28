from __future__ import annotations

import hashlib
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole
from knowloop_api.main import create_app
from knowloop_api.services.learning import (
    LearningNote,
    build_learning_notes_path,
    upsert_learning_note,
)
from knowloop_api.services.sessions import SessionRecord, save_session


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
    request_id: str = "req-test-learning-scope",
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


def make_student_session(
    *,
    session_id: str,
    user_id: str,
    answer: str,
    created_at: datetime,
    course_id: str = "course-calculus-1",
    class_id: str = "class-calculus-1-2026-spring-a",
) -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        role=ActorRole.STUDENT,
        user_id=user_id,
        course_id=course_id,
        class_id=class_id,
        question="How should I study this?",
        answer=answer,
        created_at=created_at,
        tags=["learning"],
    )


def test_learning_self_filters_cross_scope_session_refs(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    minji_session = make_student_session(
        session_id="ses-student-stu-kim-minji-class-calculus-1-2026-spring-a-20260408T091000Z",
        user_id="stu-kim-minji",
        answer="Minji should review the chain rule examples.",
        created_at=datetime(2026, 4, 8, 9, 10, tzinfo=UTC),
    )
    doyun_session = make_student_session(
        session_id="ses-student-stu-park-doyun-class-calculus-1-2026-spring-a-20260408T092000Z",
        user_id="stu-park-doyun",
        answer="Doyun private answer should not appear in Minji learning console.",
        created_at=datetime(2026, 4, 8, 9, 20, tzinfo=UTC),
    )
    save_session(settings, minji_session, request_id="req-save-minji-session")
    save_session(settings, doyun_session, request_id="req-save-doyun-session")
    upsert_learning_note(
        settings,
        LearningNote(
            learning_note_id=(
                "learn-stu-kim-minji-calculus-1-calculus-1-2026-spring-a"
            ),
            student_id="stu-kim-minji",
            course_id="course-calculus-1",
            class_id="class-calculus-1-2026-spring-a",
            actor_role=ActorRole.STUDENT,
            concepts=["chain rule"],
            gaps=["Needs more composition practice."],
            next_actions=["Review chain rule wiki"],
            session_refs=[doyun_session.session_id, minji_session.session_id],
            summary="Minji is practicing chain rule composition.",
            created_at=datetime(2026, 4, 8, 9, 30, tzinfo=UTC),
        ),
        actor_id="stu-kim-minji",
        request_id="req-save-learning-note",
    )

    response = client.get(
        "/api/v1/learning/self",
        headers=build_headers(role="student", actor_id="stu-kim-minji"),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["session_ref_count"] == 1
    assert data["learning_note"]["learning_note_id"] == (
        "learn-stu-kim-minji-calculus-1-calculus-1-2026-spring-a"
    )
    assert data["learning_note"]["session_refs"] == [minji_session.session_id]
    assert "learn-stu-park-doyun" not in str(data)
    assert data["confusion_signals"][0]["linked_session_id"] == minji_session.session_id
    assert data["learning_notes"][0]["linked_session_id"] == minji_session.session_id
    assert [item["session_id"] for item in data["recent_sessions"]] == [
        minji_session.session_id
    ]
    assert "Doyun private answer" not in str(data)


def test_learning_self_ignores_note_with_mismatched_frontmatter_scope(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    upsert_learning_note(
        settings,
        LearningNote(
            learning_note_id=(
                "learn-stu-kim-minji-calculus-1-calculus-1-2026-spring-a"
            ),
            student_id="stu-kim-minji",
            course_id="course-calculus-1",
            class_id="class-calculus-1-2026-spring-a",
            actor_role=ActorRole.STUDENT,
            concepts=["chain rule"],
            gaps=["Needs more practice."],
            next_actions=["Ask a follow-up question"],
            session_refs=[],
            summary="Scope mismatch test note.",
            created_at=datetime(2026, 4, 8, 9, 30, tzinfo=UTC),
        ),
        actor_id="stu-kim-minji",
        request_id="req-save-learning-note-scope-mismatch",
    )
    notes_path = build_learning_notes_path(
        settings,
        student_id="stu-kim-minji",
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
    )
    notes_path.write_text(
        notes_path.read_text(encoding="utf-8").replace(
            "student_id: stu-kim-minji",
            "student_id: stu-park-doyun",
        ),
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/learning/self",
        headers=build_headers(role="student", actor_id="stu-kim-minji"),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["session_ref_count"] == 0
    assert data["learning_note"] is None
    assert data["recent_sessions"] == []


def test_learning_self_normalizes_rendered_learning_note_id_to_context_scope(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    upsert_learning_note(
        settings,
        LearningNote(
            learning_note_id=(
                "learn-stu-kim-minji-calculus-1-calculus-1-2026-spring-a"
            ),
            student_id="stu-kim-minji",
            course_id="course-calculus-1",
            class_id="class-calculus-1-2026-spring-a",
            actor_role=ActorRole.STUDENT,
            concepts=["chain rule"],
            gaps=["Needs more practice."],
            next_actions=["Ask a follow-up question"],
            session_refs=[],
            summary="Learning note identity normalization test.",
            created_at=datetime(2026, 4, 8, 9, 30, tzinfo=UTC),
        ),
        actor_id="stu-kim-minji",
        request_id="req-save-learning-note-id-normalization",
    )
    notes_path = build_learning_notes_path(
        settings,
        student_id="stu-kim-minji",
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
    )
    notes_path.write_text(
        notes_path.read_text(encoding="utf-8").replace(
            "learning_note_id: learn-stu-kim-minji-calculus-1-calculus-1-2026-spring-a",
            "learning_note_id: learn-stu-park-doyun-calculus-1-calculus-1-2026-spring-a",
        ),
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/learning/self",
        headers=build_headers(role="student", actor_id="stu-kim-minji"),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["learning_note"]["learning_note_id"] == (
        "learn-stu-kim-minji-calculus-1-calculus-1-2026-spring-a"
    )
    assert data["learning_notes"][0]["note_id"] == (
        "learn-stu-kim-minji-calculus-1-calculus-1-2026-spring-a"
    )
    assert data["confusion_signals"][0]["signal_id"].startswith(
        "learn-stu-kim-minji-calculus-1-calculus-1-2026-spring-a"
    )
    assert "learn-stu-park-doyun" not in str(data)
