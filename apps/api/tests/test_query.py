from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole, RequestDomain, SourceType
from knowloop_api.core.frontmatter import parse_frontmatter_document
from knowloop_api.db.audit import list_audit_events
from knowloop_api.db.manifest import list_source_records
from knowloop_api.main import create_app
from knowloop_api.services import query as query_service
from knowloop_api.services.candidates import CandidateKind, CandidateStatus, list_candidates
from knowloop_api.services.learning import get_learning_note
from knowloop_api.services.sessions import SessionRecord, get_session, save_session
from knowloop_api.services.sources import SourceRegistrationInput, register_source

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "data" / "fixtures"
QUERY_FIXTURE_NAMES = (
    "student-chain-rule-confusion.json",
    "student-homework-deadline-01.json",
    "student-homework-deadline-02.json",
    "student-unresolved-question.json",
    "operator-refund-policy.json",
    "instructor-homework-faq.json",
)


def build_settings(tmp_path: Path) -> Settings:
    digest = hashlib.sha1(str(tmp_path).encode("utf-8")).hexdigest()[:10]
    data_root = Path(tempfile.gettempdir()) / "kl" / digest
    shutil.rmtree(data_root, ignore_errors=True)
    return Settings(data_root=data_root)


def build_client(tmp_path: Path) -> tuple[TestClient, Settings]:
    settings = build_settings(tmp_path)
    return TestClient(create_app(settings), raise_server_exceptions=False), settings


def seed_query_runtime(settings: Settings) -> None:
    source_id_map = _seed_sources(settings)
    _seed_wiki(settings, source_id_map)
    _seed_sessions(settings, source_id_map)


def _seed_sources(settings: Settings) -> dict[str, str]:
    source_id_map: dict[str, str] = {}
    for source_file in sorted((FIXTURE_ROOT / "sources").glob("*.md")):
        contents = source_file.read_text(encoding="utf-8")
        metadata, _body = parse_frontmatter_document(contents)
        source_type = SourceType(str(metadata["source_type"]))
        actor_role = ActorRole(str(metadata["actor_role"]))
        requested_domain = (
            RequestDomain.OPERATIONS
            if source_type is SourceType.OPERATIONS_NOTE
            else RequestDomain.ACADEMIC
        )

        registered = register_source(
            settings,
            SourceRegistrationInput(
                source_type=source_type,
                title=str(metadata["title"]),
                content=contents,
                mime_type="text/markdown",
                filename=source_file.name,
            ),
            course_id=str(metadata["course_id"]),
            class_id=str(metadata["class_id"]),
            actor_role=actor_role,
            actor_id=_seed_actor_id(actor_role),
            domain=requested_domain,
            created_at=_parse_timestamp(str(metadata["created_at"])),
        )
        source_id_map[str(metadata["source_id"])] = registered.source_id
    return source_id_map


def _seed_wiki(settings: Settings, source_id_map: dict[str, str]) -> None:
    for wiki_file in sorted((FIXTURE_ROOT / "wiki").glob("*.seed.md")):
        contents = wiki_file.read_text(encoding="utf-8")
        for fixture_source_id, runtime_source_id in source_id_map.items():
            contents = contents.replace(fixture_source_id, runtime_source_id)
        metadata, _body = parse_frontmatter_document(contents)
        destination = (
            settings.data_root
            / "wiki"
            / str(metadata["domain"])
            / _wiki_slug_from_fixture_name(wiki_file.name)
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(contents, encoding="utf-8")


def _seed_sessions(settings: Settings, source_id_map: dict[str, str]) -> None:
    for session_file in sorted((FIXTURE_ROOT / "sessions").glob("*.json")):
        session_payload = json.loads(session_file.read_text(encoding="utf-8"))
        for item in session_payload:
            for source_ref in item.get("source_refs", []):
                source_ref["source_id"] = source_id_map.get(
                    source_ref["source_id"], source_ref["source_id"]
                )
            save_session(settings, SessionRecord.model_validate(item))


def _seed_actor_id(actor_role: ActorRole) -> str:
    if actor_role is ActorRole.INSTRUCTOR:
        return "ins-calculus-team"
    if actor_role is ActorRole.OPERATOR:
        return "ops-academic-office"
    return "system-seed"


def _wiki_slug_from_fixture_name(file_name: str) -> str:
    stem = file_name.removesuffix(".seed.md")
    return "-".join(stem.split("-")[1:]) + ".md"


def _parse_timestamp(value: str):
    return __import__("datetime").datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.mark.parametrize(
    "fixture_name",
    QUERY_FIXTURE_NAMES,
)
def test_query_endpoint_matches_fixture_expectations(
    tmp_path: Path,
    fixture_name: str,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)
    fixture = json.loads((FIXTURE_ROOT / "queries" / fixture_name).read_text(encoding="utf-8"))
    expected = fixture["expected"]

    response = client.post(
        "/api/v1/query/respond",
        headers=fixture["request_headers"],
        json=fixture["request_body"],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == fixture["request_headers"]["X-Request-Id"]
    assert payload["data"]["answer"]
    assert payload["data"]["answer_basis"] == expected["answer_basis"]
    assert [item["entity_type"] for item in payload["data"]["retrieval_refs"]] == expected[
        "retrieval_entity_types"
    ]
    assert [
        {
            "kind": item["kind"],
            "action": item["action"],
            "status": item["status"],
        }
        for item in payload["data"]["writeback_plan"]
    ] == expected["writeback_plan"]
    if fixture["request_headers"]["X-Knowloop-Role"] == "student":
        assert all(
            item["entity_type"] != "raw_source" for item in payload["data"]["retrieval_refs"]
        )
        assert all(not item["source_refs"] for item in payload["data"]["retrieval_refs"])
    elif "raw_source" in expected["retrieval_entity_types"]:
        raw_source_refs = [
            item
            for item in payload["data"]["retrieval_refs"]
            if item["entity_type"] == "raw_source"
        ]
        assert raw_source_refs
        assert all(item["source_refs"] for item in raw_source_refs)

    session_id = payload["data"]["session_id"]
    stored_session = get_session(settings, session_id)
    assert stored_session.question == fixture["request_body"]["message"]
    session_writeback = next(
        item for item in payload["data"]["writeback_plan"] if item["kind"] == "session"
    )
    assert session_writeback["target_id"] == session_id

    expected_candidate = expected.get("candidate")
    candidate = None
    if expected_candidate is not None:
        candidate_records = list_candidates(
            settings, class_id=fixture["request_headers"]["X-Knowloop-Class-Id"]
        )
        candidate = next(item for item in candidate_records if session_id in item.session_refs)
        assert candidate.kind is CandidateKind(expected_candidate["kind"])
        assert candidate.status is CandidateStatus(expected_candidate["status"])
        assert candidate.related_page_id == expected_candidate["related_page_id"]
        assert candidate.confidence >= expected_candidate["min_confidence"]
        assert len(candidate.source_refs) >= expected_candidate["min_source_ref_count"]
        assert len(candidate.session_refs) >= expected_candidate["min_session_ref_count"]
        candidate_writeback = next(
            item for item in payload["data"]["writeback_plan"] if item["kind"] == "candidate"
        )
        assert candidate_writeback["target_id"] == candidate.candidate_id
    else:
        assert all(item["kind"] != "candidate" for item in payload["data"]["writeback_plan"])

    learning_note = get_learning_note(
        settings,
        student_id=fixture["request_headers"]["X-Knowloop-Actor-Id"],
        course_id=fixture["request_headers"]["X-Knowloop-Course-Id"],
        class_id=fixture["request_headers"]["X-Knowloop-Class-Id"],
    )
    if expected["learning_note_written"]:
        assert learning_note is not None
        assert learning_note.gaps
        learning_note_expectation = expected.get("learning_note")
        if learning_note_expectation is not None:
            assert learning_note.learning_note_id == learning_note_expectation["learning_note_id"]
            assert any(
                learning_note_expectation["concept_contains"] in concept
                for concept in learning_note.concepts
            )
        assert stored_session.learning_note_refs == [learning_note.learning_note_id]
        learning_writeback = next(
            item for item in payload["data"]["writeback_plan"] if item["kind"] == "learning_note"
        )
        assert learning_writeback["target_id"] == learning_note.learning_note_id
    else:
        assert learning_note is None
        assert stored_session.learning_note_refs == []
        assert all(item["kind"] != "learning_note" for item in payload["data"]["writeback_plan"])

    if candidate is not None:
        assert stored_session.candidate_refs == [candidate.candidate_id]
    else:
        assert stored_session.candidate_refs == []

    audit_actions = {event.action for event in list_audit_events(settings, entity_id=session_id)}
    assert "session_saved" in audit_actions


def test_query_endpoint_returns_insufficient_verified_context_when_fallback_is_disabled(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    response = client.post(
        "/api/v1/query/respond",
        headers={
            "X-Knowloop-Role": "student",
            "X-Knowloop-Actor-Id": "stu-kim-minji",
            "X-Knowloop-Course-Id": "course-calculus-1",
            "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
            "X-Knowloop-Domain": "academic",
            "X-Request-Id": "req-query-no-fallback",
        },
        json={
            "message": "What is the convergence test for this sequence?",
            "attachment_source_ids": [],
            "allow_raw_source_fallback": False,
            "response_mode": "default",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "insufficient_verified_context"


def test_query_endpoint_wraps_blank_message_validation_in_contract_envelope(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.post(
        "/api/v1/query/respond",
        headers={
            "X-Knowloop-Role": "student",
            "X-Knowloop-Actor-Id": "stu-kim-minji",
            "X-Knowloop-Course-Id": "course-calculus-1",
            "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
            "X-Knowloop-Domain": "academic",
            "X-Request-Id": "req-query-blank-message",
        },
        json={
            "message": "   ",
            "attachment_source_ids": [],
            "allow_raw_source_fallback": False,
            "response_mode": "default",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_query_endpoint_rejects_student_raw_source_attachments(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)
    source_id = list_source_records(settings)[0].source_id

    response = client.post(
        "/api/v1/query/respond",
        headers={
            "X-Knowloop-Role": "student",
            "X-Knowloop-Actor-Id": "stu-kim-minji",
            "X-Knowloop-Course-Id": "course-calculus-1",
            "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
            "X-Knowloop-Domain": "academic",
            "X-Request-Id": "req-query-student-attachment",
        },
        json={
            "message": "Can you check this source for me?",
            "attachment_source_ids": [source_id],
            "allow_raw_source_fallback": True,
            "response_mode": "default",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_scope"


def test_query_endpoint_uses_formal_wiki_only_for_homework_when_fallback_is_disabled(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    response = client.post(
        "/api/v1/query/respond",
        headers={
            "X-Knowloop-Role": "student",
            "X-Knowloop-Actor-Id": "stu-park-jiyoon",
            "X-Knowloop-Course-Id": "course-calculus-1",
            "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
            "X-Knowloop-Domain": "academic",
            "X-Request-Id": "req-query-homework-wiki-only",
        },
        json={
            "message": "When is Homework 01 due?",
            "attachment_source_ids": [],
            "allow_raw_source_fallback": False,
            "response_mode": "default",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["answer_basis"] == ["formal_wiki"]
    answer = response.json()["data"]["answer"]
    assert "Homework 01 is due" in answer
    assert "Friday, April 10 at 11:59 PM KST" in answer
    assert "LMS assignment page" in answer


def test_query_endpoint_rejects_reused_idempotency_key_with_different_payloads(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)
    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
        "X-Request-Id": "req-query-replay-conflict-01",
        "Idempotency-Key": "idem-query-replay-conflict",
    }

    first = client.post(
        "/api/v1/query/respond",
        headers=headers,
        json={
            "message": (
                "I still do not understand when the chain rule is different "
                "from the product rule."
            ),
            "attachment_source_ids": [],
            "allow_raw_source_fallback": True,
            "response_mode": "default",
        },
    )
    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-replay-conflict-02"},
        json={
            "message": "When is Homework 01 due?",
            "attachment_source_ids": [],
            "allow_raw_source_fallback": False,
            "response_mode": "default",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_action"


def test_query_endpoint_replays_same_idempotent_request_without_duplicate_candidate(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)
    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
        "Idempotency-Key": "idem-query-replay-same",
    }
    body = {
        "message": (
            "I still do not understand when the chain rule is different "
            "from the product rule."
        ),
        "attachment_source_ids": [],
        "allow_raw_source_fallback": True,
        "response_mode": "default",
    }

    first = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-replay-same-01"},
        json=body,
    )
    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-replay-same-02"},
        json=body,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["session_id"] == second.json()["data"]["session_id"]
    first_targets = {
        item["kind"]: item["target_id"] for item in first.json()["data"]["writeback_plan"]
    }
    second_targets = {
        item["kind"]: item["target_id"] for item in second.json()["data"]["writeback_plan"]
    }
    assert first_targets == second_targets
    assert len(
        list_candidates(
            settings,
            kind=CandidateKind.MISCONCEPTION,
            status=CandidateStatus.OPEN,
            class_id="class-calculus-1-2026-spring-a",
        )
    ) == 1
    learning_note = get_learning_note(
        settings,
        student_id="stu-kim-minji",
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
    )
    assert learning_note is not None
    assert learning_note.learning_note_id == first_targets["learning_note"]


def test_query_endpoint_audits_learning_writeback_failures(tmp_path: Path, monkeypatch) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    def fail_learning(*args, **kwargs):
        raise RuntimeError("learning backend unavailable")

    monkeypatch.setattr(query_service, "upsert_learning_note", fail_learning)

    response = client.post(
        "/api/v1/query/respond",
        headers={
            "X-Knowloop-Role": "student",
            "X-Knowloop-Actor-Id": "stu-kim-minji",
            "X-Knowloop-Course-Id": "course-calculus-1",
            "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
            "X-Knowloop-Domain": "academic",
            "X-Request-Id": "req-query-learning-failure",
        },
        json={
            "message": (
                "I still do not understand when the chain rule is different "
                "from the product rule."
            ),
            "attachment_source_ids": [],
            "allow_raw_source_fallback": True,
            "response_mode": "default",
        },
    )

    assert response.status_code == 200
    learning_plan = next(
        item
        for item in response.json()["data"]["writeback_plan"]
        if item["kind"] == "learning_note"
    )
    assert learning_plan["status"] == "failed"

    session = get_session(settings, response.json()["data"]["session_id"])
    assert session.learning_note_refs == []
    audit_actions = {
        event.action
        for event in list_audit_events(
            settings,
            entity_type="learning_note",
            entity_id="learn-stu-kim-minji-calculus-1-calculus-1-2026-spring-a",
        )
    }
    assert "learning_writeback_failed" in audit_actions


def test_query_endpoint_uses_learning_context_for_follow_up_queries(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)
    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
    }

    first = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-learning-followup-01"},
        json={
            "message": (
                "I still do not understand when the chain rule is different "
                "from the product rule."
            ),
            "attachment_source_ids": [],
            "allow_raw_source_fallback": True,
            "response_mode": "default",
        },
    )
    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-learning-followup-02"},
        json={
            "message": "I am still mixing up the chain rule and product rule.",
            "attachment_source_ids": [],
            "allow_raw_source_fallback": True,
            "response_mode": "default",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert "learning_context" in second.json()["data"]["answer_basis"]
    assert any(
        item["entity_type"] == "learning_note"
        for item in second.json()["data"]["retrieval_refs"]
    )
    assert "Your current learning note says to keep working on" in second.json()["data"]["answer"]


def test_query_endpoint_audits_candidate_writeback_failures(tmp_path: Path, monkeypatch) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    def fail_candidate(*args, **kwargs):
        raise RuntimeError("candidate store unavailable")

    monkeypatch.setattr(query_service, "upsert_candidate_signal", fail_candidate)

    response = client.post(
        "/api/v1/query/respond",
        headers={
            "X-Knowloop-Role": "student",
            "X-Knowloop-Actor-Id": "stu-kim-minji",
            "X-Knowloop-Course-Id": "course-calculus-1",
            "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
            "X-Knowloop-Domain": "academic",
            "X-Request-Id": "req-query-candidate-failure",
        },
        json={
            "message": (
                "I still do not understand when the chain rule is different "
                "from the product rule."
            ),
            "attachment_source_ids": [],
            "allow_raw_source_fallback": True,
            "response_mode": "default",
        },
    )

    assert response.status_code == 200
    candidate_plan = next(
        item for item in response.json()["data"]["writeback_plan"] if item["kind"] == "candidate"
    )
    assert candidate_plan["status"] == "failed"

    session = get_session(settings, response.json()["data"]["session_id"])
    assert session.candidate_refs == []
    audit_actions = {
        event.action
        for event in list_audit_events(
            settings,
            entity_type="candidate",
            entity_id=candidate_plan["target_id"],
        )
    }
    assert "candidate_writeback_failed" in audit_actions


def test_query_endpoint_audits_session_artifact_link_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    def fail_link(*args, **kwargs):
        raise RuntimeError("artifact link backend unavailable")

    monkeypatch.setattr(query_service, "update_session_artifact_refs", fail_link)

    response = client.post(
        "/api/v1/query/respond",
        headers={
            "X-Knowloop-Role": "student",
            "X-Knowloop-Actor-Id": "stu-kim-minji",
            "X-Knowloop-Course-Id": "course-calculus-1",
            "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
            "X-Knowloop-Domain": "academic",
            "X-Request-Id": "req-query-artifact-link-failure",
        },
        json={
            "message": (
                "I still do not understand when the chain rule is different "
                "from the product rule."
            ),
            "attachment_source_ids": [],
            "allow_raw_source_fallback": True,
            "response_mode": "default",
        },
    )

    assert response.status_code == 200
    session_id = response.json()["data"]["session_id"]
    session = get_session(settings, session_id)
    assert session.learning_note_refs == []
    assert session.candidate_refs == []
    audit_actions = {
        event.action
        for event in list_audit_events(
            settings,
            entity_type="session",
            entity_id=session_id,
        )
    }
    assert "session_artifact_link_failed" in audit_actions


def test_query_endpoint_keeps_wiki_covered_homework_queries_session_only(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)
    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-park-jiyoon",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
    }
    body = {
        "message": "When is Homework 01 due?",
        "attachment_source_ids": [],
        "allow_raw_source_fallback": False,
        "response_mode": "default",
    }

    first = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-faq-repeat-01"},
        json=body,
    )
    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-faq-repeat-02"},
        json=body,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert [item["kind"] for item in first.json()["data"]["writeback_plan"]] == ["session"]
    assert [item["kind"] for item in second.json()["data"]["writeback_plan"]] == ["session"]
    assert list_candidates(
        settings,
        kind=CandidateKind.FAQ,
        status=CandidateStatus.OPEN,
        class_id="class-calculus-1-2026-spring-a",
    ) == []


def test_query_endpoint_keeps_validator_queries_read_only_for_candidates(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    response = client.post(
        "/api/v1/query/respond",
        headers={
            "X-Knowloop-Role": "validator",
            "X-Knowloop-Actor-Id": "val-course-admin",
            "X-Knowloop-Course-Id": "course-calculus-1",
            "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
            "X-Knowloop-Domain": "review",
            "X-Request-Id": "req-query-validator-homework-review",
        },
        json={
            "message": "When is Homework 01 due?",
            "attachment_source_ids": [],
            "allow_raw_source_fallback": False,
            "response_mode": "review",
        },
    )

    assert response.status_code == 200
    assert [item["kind"] for item in response.json()["data"]["writeback_plan"]] == ["session"]
    assert list_candidates(
        settings,
        kind=CandidateKind.FAQ,
        status=CandidateStatus.OPEN,
        class_id="class-calculus-1-2026-spring-a",
    ) == []


def test_query_homework_path_ignores_instructor_sessions_when_wiki_covers_answer(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)
    instructor_session = SessionRecord(
        session_id="ses-instructor-ins-calculus-team-class-calculus-1-2026-spring-a-20260409T000000Z",
        role=ActorRole.INSTRUCTOR,
        user_id="ins-calculus-team",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        question="When is Homework 01 due?",
        answer="Use the FAQ page.",
        created_at=_parse_timestamp("2026-04-09T00:00:00Z"),
        tags=["faq"],
    )
    save_session(settings, instructor_session)

    response = client.post(
        "/api/v1/query/respond",
        headers={
            "X-Knowloop-Role": "student",
            "X-Knowloop-Actor-Id": "stu-park-jiyoon",
            "X-Knowloop-Course-Id": "course-calculus-1",
            "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
            "X-Knowloop-Domain": "academic",
            "X-Request-Id": "req-query-faq-role-boundary",
        },
        json={
            "message": "When is Homework 01 due?",
            "attachment_source_ids": [],
            "allow_raw_source_fallback": False,
            "response_mode": "default",
        },
    )

    assert response.status_code == 200
    assert [item["kind"] for item in response.json()["data"]["writeback_plan"]] == ["session"]
    assert list_candidates(
        settings,
        kind=CandidateKind.FAQ,
        status=CandidateStatus.OPEN,
        class_id="class-calculus-1-2026-spring-a",
    ) == []
