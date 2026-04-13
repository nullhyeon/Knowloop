import hashlib
import json
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole
from knowloop_api.main import create_app
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
    request_id: str = "req-test-session-search",
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


def seed_session_runtime(settings: Settings) -> None:
    for filename in (
        "student-minji-history.json",
        "student-jiyoon-history.json",
        "student-doyun-history.json",
        "operator-academic-office-history.json",
    ):
        for session in load_session_fixture(filename):
            save_session(settings, session, request_id="req-seed-session-search")


def test_student_session_search_returns_only_own_history_with_previews(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_session_runtime(settings)

    response = client.get(
        "/api/v1/sessions/search?q=chain%20rule",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-student-session-search",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 1
    hit = payload["data"][0]
    assert (
        hit["session_id"]
        == "ses-student-stu-kim-minji-class-calculus-1-2026-spring-a-20260407T133000Z"
    )
    assert hit["visibility"] == "own"
    assert "outside derivative" in hit["question_preview"]
    assert hit["answer_preview"] is not None


def test_student_session_search_does_not_return_other_students_hits(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_session_runtime(settings)

    response = client.get(
        "/api/v1/sessions/search?q=homework",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-student-session-search-homework",
        ),
    )

    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 0


def test_instructor_session_search_returns_redacted_class_hits(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_session_runtime(settings)

    response = client.get(
        "/api/v1/sessions/search?q=homework",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-instructor-session-search",
            domain="academic",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 2
    assert {item["visibility"] for item in payload["data"]} == {"class_redacted"}
    assert all(item["question_preview"] is None for item in payload["data"])
    assert all(item["answer_preview"] is None for item in payload["data"])
    assert all("Matched" in item["match_summary"] for item in payload["data"])


def test_instructor_recent_sessions_remain_redacted(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_session_runtime(settings)

    response = client.get(
        "/api/v1/sessions/recent",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-instructor-session-recent",
            domain="academic",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 4
    assert {item["visibility"] for item in payload["data"]} == {"class_redacted"}
    assert all(item["question_preview"] is None for item in payload["data"])
    assert all(item["answer_preview"] is None for item in payload["data"])


def test_operator_recent_sessions_returns_only_operations_history(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_session_runtime(settings)

    response = client.get(
        "/api/v1/sessions/recent",
        headers=build_headers(
            role="operator",
            actor_id="ops-academic-office",
            request_id="req-operator-session-recent",
            domain="operations",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 1
    hit = payload["data"][0]
    assert hit["visibility"] == "own"
    assert "refund questions" in hit["question_preview"]


def test_operator_session_search_stays_out_of_student_history(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_session_runtime(settings)

    response = client.get(
        "/api/v1/sessions/search?q=homework",
        headers=build_headers(
            role="operator",
            actor_id="ops-academic-office",
            request_id="req-operator-session-search-homework",
            domain="operations",
        ),
    )

    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 0


def test_session_search_rejects_validator_role(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_session_runtime(settings)

    response = client.get(
        "/api/v1/sessions/recent",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-validator-session-denied",
            domain="review",
        ),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_scope"



def test_session_search_uses_fts_index_for_newly_saved_sessions(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)

    session = SessionRecord(
        session_id="ses-student-stu-kim-minji-class-calculus-1-2026-spring-a-20260410T090000Z",
        role=ActorRole.STUDENT,
        user_id="stu-kim-minji",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        question="How do I use antiderivative boundary checks on this quiz?",
        answer="Focus on the antiderivative boundary value before simplifying the polynomial.",
        created_at=datetime(2026, 4, 10, 9, 0, tzinfo=UTC),
        tags=["antiderivative", "quiz"],
    )
    save_session(settings, session, request_id="req-session-search-fts")

    response = client.get(
        "/api/v1/sessions/search?q=antiderivative",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-session-search-fts",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 1
    assert payload["data"][0]["session_id"] == session.session_id

    with sqlite3.connect(settings.sessions_db_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM sessions_fts WHERE sessions_fts MATCH ?",
            ('"antiderivative"*',),
        ).fetchone()[0]

    assert count == 1


def test_session_search_fallback_preserves_total_when_query_reduces_to_stopwords(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)

    for index, question in enumerate(
        (
            "Tell me about the chain rule again.",
            "What about the homework revision window?",
        ),
        start=1,
    ):
        save_session(
            settings,
            SessionRecord(
                session_id=(
                    f"ses-student-stu-kim-minji-class-calculus-1-2026-spring-a-20260411T09000{index}Z"
                ),
                role=ActorRole.STUDENT,
                user_id="stu-kim-minji",
                class_id="class-calculus-1-2026-spring-a",
                course_id="course-calculus-1",
                question=question,
                answer="Saved for fallback total coverage.",
                created_at=datetime(2026, 4, 11, 9, 0, index, tzinfo=UTC),
                tags=["about"],
            ),
            request_id=f"req-session-search-stopword-{index}",
        )

    response = client.get(
        "/api/v1/sessions/search?q=about&limit=1",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-session-search-stopword",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 2
    assert len(payload["data"]) == 1



def test_session_search_fts_triggers_track_updates_and_deletes(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)

    session = SessionRecord(
        session_id="ses-student-stu-kim-minji-class-calculus-1-2026-spring-a-20260412T100000Z",
        role=ActorRole.STUDENT,
        user_id="stu-kim-minji",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        question="Need help with substitution strategy before the quiz.",
        answer="Start from the substitution boundary and simplify the derivative.",
        created_at=datetime(2026, 4, 12, 10, 0, tzinfo=UTC),
        tags=["substitution", "quiz"],
    )
    save_session(settings, session, request_id="req-session-search-fts-update")

    with sqlite3.connect(settings.sessions_db_path) as connection:
        connection.execute(
            "UPDATE sessions SET question = ?, tags_json = ? WHERE session_id = ?",
            (
                "Need help with tangent-line strategy before the quiz.",
                json.dumps(["tangent-line", "quiz"], ensure_ascii=False),
                session.session_id,
            ),
        )
        connection.commit()

    updated_response = client.get(
        "/api/v1/sessions/search?q=tangent-line",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-session-search-fts-updated",
        ),
    )

    assert updated_response.status_code == 200
    updated_payload = updated_response.json()
    assert updated_payload["meta"]["total"] == 1
    assert updated_payload["data"][0]["session_id"] == session.session_id

    with sqlite3.connect(settings.sessions_db_path) as connection:
        connection.execute("DELETE FROM sessions WHERE session_id = ?", (session.session_id,))
        connection.commit()

    deleted_response = client.get(
        "/api/v1/sessions/search?q=tangent-line",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-session-search-fts-deleted",
        ),
    )

    assert deleted_response.status_code == 200
    deleted_payload = deleted_response.json()
    assert deleted_payload["meta"]["total"] == 0
    assert deleted_payload["data"] == []


def test_instructor_stopword_fallback_search_is_not_capped_by_seed_window(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)

    rows = []
    for index in range(505):
        rows.append(
            (
                f"ses-student-stu-seeded-{index:03d}-class-calculus-1-2026-spring-a-20260412T120000Z",
                "student",
                f"stu-seeded-{index:03d}",
                "class-calculus-1-2026-spring-a",
                "course-calculus-1",
                f"Tell me about topic {index}.",
                "Stored for instructor fallback coverage.",
                f"2026-04-12T12:{index % 60:02d}:00Z",
                json.dumps(["about"], ensure_ascii=False),
                "[]",
                "[]",
                "[]",
                "[]",
                "null",
            )
        )

    with sqlite3.connect(settings.sessions_db_path) as connection:
        connection.executemany(
            """
            INSERT INTO sessions (
                session_id,
                role,
                user_id,
                class_id,
                course_id,
                question,
                answer,
                created_at,
                tags_json,
                source_refs_json,
                retrieval_refs_json,
                candidate_refs_json,
                learning_note_refs_json,
                replay_intent_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()

    response = client.get(
        "/api/v1/sessions/search?q=about&limit=1",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-instructor-session-search-stopword",
            domain="academic",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 505
    assert len(payload["data"]) == 1
    assert payload["data"][0]["visibility"] == "class_redacted"
