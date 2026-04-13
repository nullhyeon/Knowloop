from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import threading
import time
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowloop_api.api.context import RequestContext
from knowloop_api.api.routes import query as query_route_module
from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole, RequestDomain, SourceType
from knowloop_api.core.frontmatter import parse_frontmatter_document
from knowloop_api.db.audit import (
    begin_mutation_request,
    create_audit_event,
    list_audit_events,
    list_mutation_requests,
    mark_mutation_request_applied,
    store_mutation_request_response_payload,
)
from knowloop_api.db.bootstrap import bootstrap_storage
from knowloop_api.main import create_app
from knowloop_api.services import query as query_service
from knowloop_api.services.candidates import (
    CandidateKind,
    CandidateStatus,
    list_candidates,
    promote_candidate,
)
from knowloop_api.services.learning import get_learning_note
from knowloop_api.services.sessions import (
    SessionRecord,
    get_session,
    list_recent_sessions,
    save_session,
)
from knowloop_api.services.sources import SourceRegistrationInput, register_source
from knowloop_api.services.wiki import build_wiki_page_path

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "data" / "fixtures"
QUERY_FIXTURE_NAMES = (
    "student-chain-rule-confusion.json",
    "student-chain-rule-replay.json",
    "student-chain-rule-replay-after-intervening-followup.json",
    "student-chain-rule-learning-followup.json",
    "student-chain-rule-learning-followup-replay.json",
    "student-homework-deadline-01.json",
    "student-homework-deadline-02.json",
    "student-unresolved-question.json",
    "operator-refund-policy.json",
    "instructor-homework-faq.json",
)
QUERY_ERROR_FIXTURE_NAMES = (
    "student-no-fallback-error.json",
    "student-forbidden-attachment-error.json",
    "student-chain-rule-replay-conflict.json",
)


def build_settings(tmp_path: Path, **overrides) -> Settings:
    digest = hashlib.sha1(str(tmp_path).encode("utf-8")).hexdigest()[:10]
    data_root = Path(tempfile.gettempdir()) / "kl" / digest
    shutil.rmtree(data_root, ignore_errors=True)
    return Settings(data_root=data_root, **overrides)


def build_client(tmp_path: Path, **settings_overrides) -> tuple[TestClient, Settings]:
    settings = build_settings(tmp_path, **settings_overrides)
    return TestClient(create_app(settings), raise_server_exceptions=False), settings


def seed_query_runtime(settings: Settings) -> dict[str, str]:
    source_id_map = _seed_sources(settings)
    _seed_wiki(settings, source_id_map)
    _seed_sessions(settings, source_id_map)
    return source_id_map


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
        destination = build_wiki_page_path(
            settings,
            domain=str(metadata["domain"]),
            class_scope=str(metadata["class_scope"]),
            page_id=str(metadata["page_id"]),
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


def _parse_timestamp(value: str):
    return __import__("datetime").datetime.fromisoformat(value.replace("Z", "+00:00"))


def _load_query_fixture(fixture_name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / "queries" / fixture_name).read_text(encoding="utf-8"))


def _resolve_query_request_body(
    request_body: dict[str, object],
    *,
    source_id_map: dict[str, str],
) -> dict[str, object]:
    resolved_body = deepcopy(request_body)
    attachment_source_ids = resolved_body.get("attachment_source_ids", [])
    if isinstance(attachment_source_ids, list):
        resolved_body["attachment_source_ids"] = [
            source_id_map.get(source_id, source_id) for source_id in attachment_source_ids
        ]
    return resolved_body


def _run_query_fixture_request(
    client: TestClient,
    fixture: dict[str, object],
    *,
    source_id_map: dict[str, str],
):
    return client.post(
        "/api/v1/query/respond",
        headers=fixture["request_headers"],
        json=_resolve_query_request_body(
            fixture["request_body"],
            source_id_map=source_id_map,
        ),
    )


def _clear_stored_query_response_payload(
    settings: Settings,
    *,
    session_id: str,
    idempotency_key: str,
) -> None:
    with sqlite3.connect(settings.audit_db_path) as connection:
        connection.execute(
            """
            UPDATE mutation_requests
            SET status = 'pending',
                response_json = NULL
            WHERE entity_type = 'query'
              AND entity_id = ?
              AND action = 'respond'
              AND idempotency_key = ?
            """,
            (session_id, idempotency_key),
        )
        connection.commit()


def _assert_query_mutation_request_cached(
    settings: Settings,
    *,
    session_id: str,
    idempotency_key: str,
    response_payload: dict[str, object],
) -> None:
    mutation_requests = [
        record
        for record in list_mutation_requests(settings, entity_type="query")
        if record.entity_id == session_id and record.idempotency_key == idempotency_key
    ]
    assert len(mutation_requests) == 1
    mutation_request = mutation_requests[0]
    assert mutation_request.status == "applied"
    assert mutation_request.response_payload == response_payload


def _execute_query_fixture_setup(
    client: TestClient,
    settings: Settings,
    *,
    source_id_map: dict[str, str],
    fixture: dict[str, object],
    completed: set[str] | None = None,
    active: set[str] | None = None,
) -> None:
    if completed is None:
        completed = set()
    if active is None:
        active = set()
    for setup_fixture_name in fixture.get("setup_fixtures", []):
        if setup_fixture_name in completed:
            continue
        if setup_fixture_name in active:
            raise AssertionError(f"Cyclic query fixture setup detected: {setup_fixture_name}")
        active.add(setup_fixture_name)
        setup_fixture = _load_query_fixture(setup_fixture_name)
        _execute_query_fixture_setup(
            client,
            settings,
            source_id_map=source_id_map,
            fixture=setup_fixture,
            completed=completed,
            active=active,
        )
        _assert_query_fixture(
            client,
            settings,
            setup_fixture,
            source_id_map=source_id_map,
            completed=completed,
            active=active,
        )
        active.remove(setup_fixture_name)
        completed.add(setup_fixture_name)


def _capture_query_side_effects(
    settings: Settings,
    *,
    actor_id: str,
    course_id: str,
    class_id: str,
    role: str,
    request_id: str | None,
    idempotency_key: str | None,
) -> dict[str, object]:
    sessions = list_recent_sessions(
        settings,
        user_id=actor_id,
        course_id=course_id,
        class_id=class_id,
        limit=100,
    )
    candidates = [
        candidate
        for candidate in list_candidates(settings, class_id=class_id)
        if candidate.course_id == course_id
    ]
    learning_note = (
        get_learning_note(
            settings,
            student_id=actor_id,
            course_id=course_id,
            class_id=class_id,
        )
        if role == "student"
        else None
    )
    request_audit_events = (
        [
            event
            for event in list_audit_events(settings)
            if event.request_id == request_id
        ]
        if request_id is not None
        else []
    )
    mutation_requests = (
        [
            record
            for record in list_mutation_requests(settings, entity_type="query")
            if record.idempotency_key == idempotency_key
        ]
        if idempotency_key is not None
        else []
    )
    return {
        "session_count": len(sessions),
        "session_ids": {session.session_id for session in sessions},
        "candidate_count": len(candidates),
        "candidate_ids": {candidate.candidate_id for candidate in candidates},
        "learning_note_snapshot": (
            learning_note.model_dump(mode="json") if learning_note is not None else None
        ),
        "request_audit_count": len(request_audit_events),
        "mutation_request_count": len(mutation_requests),
    }


def _assert_query_fixture(
    client: TestClient,
    settings: Settings,
    fixture: dict[str, object],
    *,
    source_id_map: dict[str, str],
    completed: set[str] | None = None,
    active: set[str] | None = None,
) -> None:
    _execute_query_fixture_setup(
        client,
        settings,
        source_id_map=source_id_map,
        fixture=fixture,
        completed=completed,
        active=active,
    )
    before = _capture_query_side_effects(
        settings,
        actor_id=fixture["request_headers"]["X-Knowloop-Actor-Id"],
        course_id=fixture["request_headers"]["X-Knowloop-Course-Id"],
        class_id=fixture["request_headers"]["X-Knowloop-Class-Id"],
        role=fixture["request_headers"]["X-Knowloop-Role"],
        request_id=None,
        idempotency_key=fixture["request_headers"].get("Idempotency-Key"),
    )
    response = _run_query_fixture_request(
        client,
        fixture,
        source_id_map=source_id_map,
    )
    response_request_id = response.json()["request_id"]
    after = _capture_query_side_effects(
        settings,
        actor_id=fixture["request_headers"]["X-Knowloop-Actor-Id"],
        course_id=fixture["request_headers"]["X-Knowloop-Course-Id"],
        class_id=fixture["request_headers"]["X-Knowloop-Class-Id"],
        role=fixture["request_headers"]["X-Knowloop-Role"],
        request_id=response_request_id,
        idempotency_key=fixture["request_headers"].get("Idempotency-Key"),
    )

    expected = fixture["expected"]
    if "error" in expected:
        _assert_query_error_fixture(
            fixture,
            response=response,
            before=before,
            after=after,
        )
        return

    _assert_query_success_fixture(
        settings,
        fixture,
        response=response,
        before=before,
        after=after,
    )


def _assert_query_error_fixture(
    fixture: dict[str, object],
    *,
    response,
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    expected = fixture["expected"]

    assert response.status_code == expected["status_code"]
    payload = response.json()
    assert payload["request_id"]
    assert response.headers["X-Request-Id"] == payload["request_id"]
    assert payload["error"]["code"] == expected["error"]["code"]
    assert expected["error"]["message_contains"] in payload["error"]["message"]

    side_effects = expected.get("side_effects")
    if side_effects is None:
        return

    assert after["session_count"] - before["session_count"] == side_effects["session_delta"]
    assert after["candidate_count"] - before["candidate_count"] == side_effects[
        "candidate_delta"
    ]
    if side_effects["session_delta"] == 0:
        assert after["session_ids"] == before["session_ids"]
    if side_effects["candidate_delta"] == 0:
        assert after["candidate_ids"] == before["candidate_ids"]
    if side_effects.get("learning_note_unchanged"):
        assert after["learning_note_snapshot"] == before["learning_note_snapshot"]
    if "request_audit_delta" in side_effects:
        assert after["request_audit_count"] - before["request_audit_count"] == side_effects[
            "request_audit_delta"
        ]
    assert after["mutation_request_count"] - before["mutation_request_count"] == side_effects[
        "mutation_request_delta"
    ]


def _assert_query_success_fixture(
    settings: Settings,
    fixture: dict[str, object],
    *,
    response,
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    expected = fixture["expected"]
    side_effects = expected["side_effects"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"]
    assert response.headers["X-Request-Id"] == payload["request_id"]
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
    _assert_query_replay_intent_contract(
        settings,
        fixture=fixture,
        stored_session=stored_session,
        answer_basis=expected["answer_basis"],
        expects_learning=expected["learning_note_written"],
        expects_candidate=expected.get("candidate") is not None,
    )
    assert stored_session.question == fixture["request_body"]["message"]
    session_writeback = next(
        item for item in payload["data"]["writeback_plan"] if item["kind"] == "session"
    )
    assert session_writeback["target_id"] == session_id
    expected_session_delta = side_effects.get("session_delta", 1)
    assert after["session_count"] - before["session_count"] == expected_session_delta
    if expected_session_delta == 0:
        assert session_id in before["session_ids"]
    else:
        assert session_id not in before["session_ids"]
    assert session_id in after["session_ids"]

    expected_candidate = expected.get("candidate")
    candidate = None
    candidate_delta = after["candidate_count"] - before["candidate_count"]
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
        if "candidate_delta" in side_effects:
            assert candidate_delta == side_effects["candidate_delta"]
        elif candidate_writeback["action"] == "create":
            assert candidate_delta == 1
            assert candidate.candidate_id not in before["candidate_ids"]
        else:
            assert candidate_delta == 0
            assert candidate.candidate_id in before["candidate_ids"]
        assert candidate.candidate_id in after["candidate_ids"]
    else:
        assert candidate_delta == 0
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
            if "learning_note_id" in learning_note_expectation:
                assert (
                    learning_note.learning_note_id
                    == learning_note_expectation["learning_note_id"]
                )
            if "min_session_ref_count" in learning_note_expectation:
                assert len(learning_note.session_refs) >= learning_note_expectation[
                    "min_session_ref_count"
                ]
            assert any(
                learning_note_expectation["concept_contains"] in concept
                for concept in learning_note.concepts
            )
        if side_effects.get("learning_note_unchanged"):
            assert before["learning_note_snapshot"] == after["learning_note_snapshot"]
        else:
            assert before["learning_note_snapshot"] != after["learning_note_snapshot"]
        assert stored_session.learning_note_refs == [learning_note.learning_note_id]
        learning_writeback = next(
            item for item in payload["data"]["writeback_plan"] if item["kind"] == "learning_note"
        )
        assert learning_writeback["target_id"] == learning_note.learning_note_id
    else:
        assert learning_note is None
        assert before["learning_note_snapshot"] == after["learning_note_snapshot"]
        assert stored_session.learning_note_refs == []
        assert all(item["kind"] != "learning_note" for item in payload["data"]["writeback_plan"])

    if candidate is not None:
        assert stored_session.candidate_refs == [candidate.candidate_id]
    else:
        assert stored_session.candidate_refs == []

    if "request_audit_delta" in side_effects:
        assert after["request_audit_count"] - before["request_audit_count"] == side_effects[
            "request_audit_delta"
        ]
    else:
        assert after["request_audit_count"] > before["request_audit_count"]
        audit_actions = {
            event.action for event in list_audit_events(settings, entity_id=session_id)
        }
        assert "session_saved" in audit_actions
    assert after["mutation_request_count"] - before["mutation_request_count"] == side_effects[
        "mutation_request_delta"
    ]
    idempotency_key = fixture["request_headers"].get("Idempotency-Key")
    if idempotency_key is not None:
        mutation_requests = [
            record
            for record in list_mutation_requests(settings, entity_type="query")
            if record.idempotency_key == idempotency_key
        ]
        assert len(mutation_requests) == 1
        mutation_request = mutation_requests[0]
        assert mutation_request.status == side_effects["mutation_request_status"]
        if side_effects.get("stored_response_payload"):
            assert mutation_request.response_payload == payload["data"]


def _assert_query_replay_intent_contract(
    settings: Settings,
    *,
    fixture: dict[str, object],
    stored_session: SessionRecord,
    answer_basis: list[str],
    expects_learning: bool,
    expects_candidate: bool,
) -> None:
    replay_intent = stored_session.replay_intent
    assert isinstance(replay_intent, dict)
    assert replay_intent["contract_version"] == 1
    assert replay_intent["answer_basis"] == answer_basis
    assert replay_intent["idempotency_key"] == fixture["request_headers"].get("Idempotency-Key")
    assert [
        {
            "kind": item["kind"],
            "action": item["action"],
            "status": item["status"],
        }
        for item in replay_intent["writeback_plan"]
    ] == fixture["expected"]["writeback_plan"]

    learning_payload = replay_intent.get("learning_proposal")
    candidate_payload = replay_intent.get("candidate_proposal")
    if expects_learning:
        assert isinstance(learning_payload, dict)
        assert {
            "learning_note_id",
            "student_id",
            "course_id",
            "class_id",
            "concepts",
            "gaps",
            "next_actions",
            "source_refs",
            "session_refs",
            "created_at",
        }.issubset(learning_payload)
    else:
        assert learning_payload is None

    if expects_candidate:
        assert isinstance(candidate_payload, dict)
        assert {
            "candidate_id",
            "kind",
            "status",
            "title",
            "summary",
            "class_id",
            "course_id",
            "confidence",
            "source_refs",
            "session_refs",
            "created_at",
            "updated_at",
        }.issubset(candidate_payload)
    else:
        assert candidate_payload is None

    session_saved_events = list_audit_events(
        settings,
        entity_type="session",
        entity_id=stored_session.session_id,
        action="session_saved",
    )
    assert session_saved_events
    session_saved_details = session_saved_events[0].details
    assert isinstance(session_saved_details, dict)
    assert session_saved_details["contract_version"] == 1
    assert session_saved_details["answer_basis"] == answer_basis
    assert session_saved_details["idempotency_key"] == fixture["request_headers"].get(
        "Idempotency-Key"
    )


def test_save_session_raises_for_identical_existing_row_when_recovery_requests_it(
    tmp_path: Path,
) -> None:
    _client, settings = build_client(tmp_path)
    session = SessionRecord(
        session_id="ses-student-stu-kim-minji-class-calculus-1-2026-spring-a-20260410T000000Z",
        role=ActorRole.STUDENT,
        user_id="stu-kim-minji",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        question="When is Homework 01 due?",
        answer="Homework 01 is due Friday.",
        created_at=_parse_timestamp("2026-04-10T00:00:00Z"),
        tags=["faq"],
    )

    save_session(settings, session)

    with pytest.raises(FileExistsError):
        save_session(settings, session, raise_on_existing=True)


def test_build_query_session_id_scopes_idempotent_requests_by_course_and_domain() -> None:
    created_at = _parse_timestamp("2026-04-10T00:00:00Z")
    base_context = RequestContext(
        role=ActorRole.STUDENT,
        actor_id="stu-kim-minji",
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        domain=RequestDomain.ACADEMIC,
        request_id="req-query-session-scope-01",
        idempotency_key="idem-query-scope-test",
    )

    same_scope_session_id = query_service._build_query_session_id(
        context=base_context,
        request_fingerprint="fingerprint-a",
        created_at=created_at,
    )
    different_course_session_id = query_service._build_query_session_id(
        context=base_context.model_copy(update={"course_id": "course-calculus-2"}),
        request_fingerprint="fingerprint-a",
        created_at=created_at,
    )
    different_domain_session_id = query_service._build_query_session_id(
        context=base_context.model_copy(update={"domain": RequestDomain.REVIEW}),
        request_fingerprint="fingerprint-a",
        created_at=created_at,
    )

    assert same_scope_session_id == query_service._build_query_session_id(
        context=base_context,
        request_fingerprint="fingerprint-b",
        created_at=created_at,
    )
    assert different_course_session_id != same_scope_session_id
    assert different_domain_session_id != same_scope_session_id


def test_query_request_normalizes_replay_relevant_fields() -> None:
    request = query_service.QueryRequest.model_validate(
        {
            "message": "  Explain the chain rule again.  ",
            "attachment_source_ids": ["src-b", " src-a ", "src-b"],
            "allow_raw_source_fallback": True,
            "response_mode": "teaching",
        }
    )

    assert request.message == "Explain the chain rule again."
    assert request.attachment_source_ids == ["src-a", "src-b"]


def test_list_replay_audits_uses_frozen_targets_not_original_request_scope(
    tmp_path: Path,
) -> None:
    _client, settings = build_client(tmp_path)
    replay_intent = query_service.QueryReplayIntent(
        answer_basis=["formal_wiki"],
        idempotency_key="idem-shared-replay-scope",
    )
    session_saved_audit = create_audit_event(
        settings,
        entity_type="session",
        entity_id="ses-replay-scope",
        action="session_saved",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-query-engine",
        request_id="req-shared-scope-a",
        idempotency_key="idem-shared-replay-scope",
        details=replay_intent.model_dump(mode="json", exclude_none=False),
        created_at=_parse_timestamp("2026-04-10T12:00:00Z"),
    )
    create_audit_event(
        settings,
        entity_type="learning_note",
        entity_id="learn-shared-scope-a",
        action="learning_generated",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-query-engine",
        request_id="req-shared-scope-a",
        idempotency_key="idem-shared-replay-scope",
        created_at=_parse_timestamp("2026-04-10T12:00:01Z"),
    )
    create_audit_event(
        settings,
        entity_type="learning_note",
        entity_id="learn-shared-scope-b",
        action="learning_generated",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-query-engine",
        request_id="req-shared-scope-b",
        idempotency_key="idem-shared-replay-scope",
        created_at=_parse_timestamp("2026-04-10T12:00:02Z"),
    )

    replay_audits = query_service._list_replay_audits(
        settings,
        replay_intent=replay_intent,
        session_id="ses-replay-scope",
        session_saved_audit=session_saved_audit,
    )

    assert replay_audits
    assert {event.request_id for event in replay_audits} == {"req-shared-scope-a"}
    assert {event.entity_id for event in replay_audits} == {"ses-replay-scope"}


def test_list_replay_audits_does_not_fall_back_to_foreign_same_key_audits(
    tmp_path: Path,
) -> None:
    _client, settings = build_client(tmp_path)
    replay_intent = query_service.QueryReplayIntent(
        answer_basis=["formal_wiki"],
        idempotency_key="idem-shared-replay-no-fallback",
    )
    session_saved_audit = create_audit_event(
        settings,
        entity_type="session",
        entity_id="ses-replay-no-fallback",
        action="session_saved",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-query-engine",
        request_id="req-shared-scope-missing",
        idempotency_key="idem-shared-replay-no-fallback",
        details=replay_intent.model_dump(mode="json", exclude_none=False),
        created_at=_parse_timestamp("2026-04-10T12:05:00Z"),
    )
    create_audit_event(
        settings,
        entity_type="learning_note",
        entity_id="learn-foreign-scope",
        action="learning_generated",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-query-engine",
        request_id="req-foreign-scope",
        idempotency_key="idem-shared-replay-no-fallback",
        created_at=_parse_timestamp("2026-04-10T12:05:01Z"),
    )

    replay_audits = query_service._list_replay_audits(
        settings,
        replay_intent=replay_intent,
        session_id="ses-replay-no-fallback",
        session_saved_audit=session_saved_audit,
    )

    assert len(replay_audits) == 1
    assert replay_audits[0].entity_type == "session"
    assert replay_audits[0].entity_id == "ses-replay-no-fallback"


def test_list_replay_audits_does_not_use_request_id_when_replay_intent_is_missing(
    tmp_path: Path,
) -> None:
    _client, settings = build_client(tmp_path)
    session_saved_audit = create_audit_event(
        settings,
        entity_type="session",
        entity_id="ses-request-id-fallback-blocked",
        action="session_saved",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-query-engine",
        request_id="req-request-id-fallback-blocked",
        idempotency_key="idem-request-id-fallback-blocked",
        details={"contract_version": 999},
        created_at=_parse_timestamp("2026-04-10T12:05:10Z"),
    )
    create_audit_event(
        settings,
        entity_type="learning_note",
        entity_id="learn-request-id-fallback-blocked",
        action="learning_generated",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-query-engine",
        request_id="req-request-id-fallback-blocked",
        idempotency_key="idem-request-id-fallback-blocked",
        created_at=_parse_timestamp("2026-04-10T12:05:11Z"),
    )

    replay_audits = query_service._list_replay_audits(
        settings,
        replay_intent=None,
        session_id="ses-request-id-fallback-blocked",
        session_saved_audit=session_saved_audit,
    )

    assert replay_audits == []


def test_get_session_saved_audit_prefers_matching_idempotency_key(tmp_path: Path) -> None:
    _client, settings = build_client(tmp_path)
    create_audit_event(
        settings,
        entity_type="session",
        entity_id="ses-owner-aware-seed",
        action="session_saved",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-query-engine",
        request_id="req-owner-aware-seed-01",
        idempotency_key="idem-owner-aware-seed-01",
        created_at=_parse_timestamp("2026-04-10T12:05:00Z"),
    )
    matching_event = create_audit_event(
        settings,
        entity_type="session",
        entity_id="ses-owner-aware-seed",
        action="session_saved",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-query-engine",
        request_id="req-owner-aware-seed-02",
        idempotency_key="idem-owner-aware-seed-02",
        created_at=_parse_timestamp("2026-04-10T12:05:05Z"),
    )

    resolved_event = query_service._get_session_saved_audit(
        settings,
        session_id="ses-owner-aware-seed",
        idempotency_key="idem-owner-aware-seed-02",
    )

    assert resolved_event == matching_event
    assert (
        query_service._get_session_saved_audit(
            settings,
            session_id="ses-owner-aware-seed",
            idempotency_key="idem-owner-aware-seed-missing",
        )
        is None
    )


def test_list_replay_audits_includes_later_same_key_repairs_for_frozen_targets(
    tmp_path: Path,
) -> None:
    _client, settings = build_client(tmp_path)
    learning_proposal = query_service.LearningReplayProposal(
        learning_note_id="learn-replay-frozen-target",
        student_id="stu-kim-minji",
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        concepts=["chain rule"],
        gaps=["chain rule vs product rule"],
        flashcards=[],
        next_actions=["Review the inner-function derivative first."],
        source_refs=[],
        session_refs=["ses-replay-frozen-target"],
        created_at=_parse_timestamp("2026-04-10T12:07:00Z"),
    )
    replay_intent = query_service.QueryReplayIntent(
        answer_basis=["formal_wiki"],
        idempotency_key="idem-shared-replay-repair",
        learning_proposal=learning_proposal,
    )
    session_saved_audit = create_audit_event(
        settings,
        entity_type="session",
        entity_id="ses-replay-frozen-target",
        action="session_saved",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-query-engine",
        request_id="req-shared-repair-original",
        idempotency_key="idem-shared-replay-repair",
        details=replay_intent.model_dump(mode="json", exclude_none=False),
        created_at=_parse_timestamp("2026-04-10T12:07:00Z"),
    )
    create_audit_event(
        settings,
        entity_type="learning_note",
        entity_id="learn-replay-frozen-target",
        action="learning_generated",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-query-engine",
        request_id="req-shared-repair-followup",
        idempotency_key="idem-shared-replay-repair",
        created_at=_parse_timestamp("2026-04-10T12:07:02Z"),
    )
    create_audit_event(
        settings,
        entity_type="learning_note",
        entity_id="learn-foreign-scope",
        action="learning_generated",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-query-engine",
        request_id="req-shared-repair-foreign",
        idempotency_key="idem-shared-replay-repair",
        created_at=_parse_timestamp("2026-04-10T12:07:03Z"),
    )
    create_audit_event(
        settings,
        entity_type="source",
        entity_id="src-unrelated-original-request",
        action="raw_source_registered",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-query-engine",
        request_id="req-shared-repair-original",
        idempotency_key="idem-shared-replay-repair",
        created_at=_parse_timestamp("2026-04-10T12:07:04Z"),
    )

    replay_audits = query_service._list_replay_audits(
        settings,
        replay_intent=replay_intent,
        session_id="ses-replay-frozen-target",
        session_saved_audit=session_saved_audit,
    )

    assert {event.entity_id for event in replay_audits} == {
        "ses-replay-frozen-target",
        "learn-replay-frozen-target",
    }
    assert {event.request_id for event in replay_audits} == {
        "req-shared-repair-original",
        "req-shared-repair-followup",
    }


def test_replay_recovery_targets_are_frozen_for_non_session_writebacks() -> None:
    response = query_service.QueryResponse(
        answer="Chain rule guidance",
        answer_basis=["formal_wiki"],
        retrieval_refs=[],
        writeback_plan=[
            query_service.WritebackPlanItem(
                kind="session",
                action="save",
                status="registered",
                target_id="ses-replay-frozen-target",
                explanation=query_service.SESSION_WRITEBACK_EXPLANATION,
            ),
            query_service.WritebackPlanItem(
                kind="candidate",
                action="create",
                status="open",
                target_id="cand-replay-frozen-target",
                explanation=query_service.CANDIDATE_WRITEBACK_EXPLANATION,
            ),
        ],
        session_id="ses-replay-frozen-target",
        created_at=_parse_timestamp("2026-04-10T12:07:00Z"),
    )
    candidate_proposal = query_service.CandidateReplayProposal(
        candidate_id="cand-replay-frozen-target",
        kind=CandidateKind.MISCONCEPTION,
        status=CandidateStatus.OPEN,
        title="Chain rule misconception",
        summary="Students are mixing chain rule and product rule.",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        confidence=0.84,
        tags=["misconception"],
        source_refs=[
            query_service.SourceRef(
                source_id="src-chain-rule",
                source_type=SourceType.LECTURE_NOTE,
            )
        ],
        session_refs=["ses-replay-frozen-target"],
        created_at=_parse_timestamp("2026-04-10T12:07:00Z"),
        updated_at=_parse_timestamp("2026-04-10T12:07:00Z"),
    ).to_candidate_item()

    assert not query_service._replay_recovery_targets_are_frozen(
        response,
        learning_proposal=None,
        candidate_proposal=None,
    )
    assert query_service._replay_recovery_targets_are_frozen(
        response,
        learning_proposal=None,
        candidate_proposal=candidate_proposal,
    )

    mismatched_response = response.model_copy(
        update={
            "writeback_plan": [
                response.writeback_plan[0],
                response.writeback_plan[1].model_copy(
                    update={"target_id": "cand-replay-frozen-target-other"}
                ),
            ]
        }
    )
    assert not query_service._replay_recovery_targets_are_frozen(
        mismatched_response,
        learning_proposal=None,
        candidate_proposal=candidate_proposal,
    )


def test_recovered_query_response_is_incomplete_when_replay_targets_are_unlinked() -> None:
    session = SessionRecord(
        session_id="ses-replay-completeness",
        role=ActorRole.STUDENT,
        user_id="stu-kim-minji",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        question="Explain the chain rule again.",
        answer="Use the outer derivative first.",
        created_at=_parse_timestamp("2026-04-10T12:11:00Z"),
        candidate_refs=[],
        learning_note_refs=[],
    )
    learning_proposal = query_service.LearningReplayProposal(
        learning_note_id="learn-replay-completeness",
        student_id="stu-kim-minji",
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        concepts=["chain rule"],
        gaps=["Differentiate the inner function explicitly."],
        flashcards=[],
        next_actions=["Practice two nested examples."],
        source_refs=[],
        session_refs=[session.session_id],
        created_at=_parse_timestamp("2026-04-10T12:11:00Z"),
    ).to_learning_note()
    candidate_proposal = query_service.CandidateReplayProposal(
        candidate_id="cand-replay-completeness",
        kind=CandidateKind.MISCONCEPTION,
        status=CandidateStatus.OPEN,
        title="Chain rule misconception",
        summary="Students are still skipping the inner derivative.",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        confidence=0.83,
        tags=["misconception"],
        source_refs=[
            query_service.SourceRef(
                source_id="src-chain-rule",
                source_type=SourceType.LECTURE_NOTE,
            )
        ],
        session_refs=[session.session_id],
        created_at=_parse_timestamp("2026-04-10T12:11:00Z"),
        updated_at=_parse_timestamp("2026-04-10T12:11:00Z"),
    ).to_candidate_item()
    response = query_service.QueryResponse(
        answer="Use the chain rule for nested functions.",
        answer_basis=["formal_wiki"],
        retrieval_refs=[],
        writeback_plan=[
            query_service.WritebackPlanItem(
                kind="session",
                action="save",
                status="registered",
                target_id=session.session_id,
                explanation=query_service.SESSION_WRITEBACK_EXPLANATION,
            ),
            query_service.WritebackPlanItem(
                kind="learning_note",
                action="update",
                status="updated",
                target_id=learning_proposal.learning_note_id,
                explanation=query_service.LEARNING_WRITEBACK_EXPLANATION,
            ),
            query_service.WritebackPlanItem(
                kind="candidate",
                action="create",
                status="open",
                target_id=candidate_proposal.candidate_id,
                explanation=query_service.CANDIDATE_WRITEBACK_EXPLANATION,
            ),
        ],
        session_id=session.session_id,
        created_at=session.created_at,
    )

    assert not query_service._recovered_query_response_is_complete(
        response,
        session=session,
        learning_proposal=learning_proposal,
        candidate_proposal=candidate_proposal,
    )

    linked_session = session.model_copy(
        update={
            "learning_note_refs": [learning_proposal.learning_note_id],
            "candidate_refs": [candidate_proposal.candidate_id],
        }
    )
    assert query_service._recovered_query_response_is_complete(
        response,
        session=linked_session,
        learning_proposal=learning_proposal,
        candidate_proposal=candidate_proposal,
    )


def test_recovered_query_response_is_incomplete_for_pending_status_empty_target_and_kind_drift(
    ) -> None:
    session = SessionRecord(
        session_id="ses-replay-completeness-guards",
        role=ActorRole.STUDENT,
        user_id="stu-kim-minji",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        question="Explain the chain rule again.",
        answer="Use the outer derivative first.",
        created_at=_parse_timestamp("2026-04-10T12:12:00Z"),
        candidate_refs=["cand-replay-completeness-guards"],
        learning_note_refs=["learn-replay-completeness-guards"],
    )
    learning_proposal = query_service.LearningReplayProposal(
        learning_note_id="learn-replay-completeness-guards",
        student_id="stu-kim-minji",
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        concepts=["chain rule"],
        gaps=["Differentiate the inner function explicitly."],
        flashcards=[],
        next_actions=["Practice two nested examples."],
        source_refs=[],
        session_refs=[session.session_id],
        created_at=_parse_timestamp("2026-04-10T12:12:00Z"),
    ).to_learning_note()
    candidate_proposal = query_service.CandidateReplayProposal(
        candidate_id="cand-replay-completeness-guards",
        kind=CandidateKind.MISCONCEPTION,
        status=CandidateStatus.OPEN,
        title="Chain rule misconception",
        summary="Students are still skipping the inner derivative.",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        confidence=0.83,
        tags=["misconception"],
        source_refs=[
            query_service.SourceRef(
                source_id="src-chain-rule",
                source_type=SourceType.LECTURE_NOTE,
            )
        ],
        session_refs=[session.session_id],
        created_at=_parse_timestamp("2026-04-10T12:12:00Z"),
        updated_at=_parse_timestamp("2026-04-10T12:12:00Z"),
    ).to_candidate_item()
    base_items = [
        query_service.WritebackPlanItem(
            kind="session",
            action="save",
            status="registered",
            target_id=session.session_id,
            explanation=query_service.SESSION_WRITEBACK_EXPLANATION,
        ),
        query_service.WritebackPlanItem(
            kind="learning_note",
            action="update",
            status="updated",
            target_id=learning_proposal.learning_note_id,
            explanation=query_service.LEARNING_WRITEBACK_EXPLANATION,
        ),
        query_service.WritebackPlanItem(
            kind="candidate",
            action="create",
            status="open",
            target_id=candidate_proposal.candidate_id,
            explanation=query_service.CANDIDATE_WRITEBACK_EXPLANATION,
        ),
    ]

    pending_response = query_service.QueryResponse(
        answer="Use the chain rule for nested functions.",
        answer_basis=["formal_wiki"],
        retrieval_refs=[],
        writeback_plan=[
            base_items[0],
            base_items[1].model_copy(update={"status": "pending"}),
            base_items[2],
        ],
        session_id=session.session_id,
        created_at=session.created_at,
    )
    assert not query_service._recovered_query_response_is_complete(
        pending_response,
        session=session,
        learning_proposal=learning_proposal,
        candidate_proposal=candidate_proposal,
    )

    empty_target_response = query_service.QueryResponse(
        answer="Use the chain rule for nested functions.",
        answer_basis=["formal_wiki"],
        retrieval_refs=[],
        writeback_plan=[
            base_items[0],
            base_items[1],
            base_items[2].model_copy(update={"target_id": ""}),
        ],
        session_id=session.session_id,
        created_at=session.created_at,
    )
    assert not query_service._recovered_query_response_is_complete(
        empty_target_response,
        session=session,
        learning_proposal=learning_proposal,
        candidate_proposal=candidate_proposal,
    )

    kind_drift_response = query_service.QueryResponse(
        answer="Use the chain rule for nested functions.",
        answer_basis=["formal_wiki"],
        retrieval_refs=[],
        writeback_plan=[base_items[0], base_items[2], base_items[1]],
        session_id=session.session_id,
        created_at=session.created_at,
    )
    assert not query_service._recovered_query_response_is_complete(
        kind_drift_response,
        session=session,
        learning_proposal=learning_proposal,
        candidate_proposal=candidate_proposal,
    )


def test_load_replayed_query_response_blocks_mismatched_frozen_targets_before_repair(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _client, settings = build_client(tmp_path)
    created_at = _parse_timestamp("2026-04-10T12:13:00Z")
    learning_proposal = query_service.LearningReplayProposal(
        learning_note_id="learn-replay-owner-guard",
        student_id="stu-kim-minji",
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        concepts=["chain rule"],
        gaps=["Differentiate the inner function explicitly."],
        flashcards=[],
        next_actions=["Practice two nested examples."],
        source_refs=[],
        session_refs=["ses-replay-owner-guard"],
        created_at=created_at,
    ).to_learning_note()
    candidate_proposal = query_service.CandidateReplayProposal(
        candidate_id="cand-replay-owner-guard",
        kind=CandidateKind.MISCONCEPTION,
        status=CandidateStatus.OPEN,
        title="Chain rule misconception",
        summary="Students are still skipping the inner derivative.",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        confidence=0.83,
        tags=["misconception"],
        source_refs=[
            query_service.SourceRef(
                source_id="src-chain-rule",
                source_type=SourceType.LECTURE_NOTE,
            )
        ],
        session_refs=["ses-replay-owner-guard"],
        created_at=created_at,
        updated_at=created_at,
    ).to_candidate_item()
    session = SessionRecord(
        session_id="ses-replay-owner-guard",
        role=ActorRole.STUDENT,
        user_id="stu-kim-minji",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        question="Explain the chain rule again.",
        answer="Use the outer derivative first.",
        created_at=created_at,
        replay_intent=query_service._build_query_session_audit_details(
            answer_basis=["formal_wiki"],
            idempotency_key="idem-replay-owner-guard",
            learning_proposal=learning_proposal,
            candidate_proposal=candidate_proposal,
            writeback_plan=[
                query_service.WritebackPlanItem(
                    kind="session",
                    action="save",
                    status="registered",
                    target_id="ses-replay-owner-guard",
                    explanation=query_service.SESSION_WRITEBACK_EXPLANATION,
                ),
                query_service.WritebackPlanItem(
                    kind="learning_note",
                    action="update",
                    status="updated",
                    target_id=learning_proposal.learning_note_id,
                    explanation=query_service.LEARNING_WRITEBACK_EXPLANATION,
                ),
                query_service.WritebackPlanItem(
                    kind="candidate",
                    action="create",
                    status="open",
                    target_id=candidate_proposal.candidate_id,
                    explanation=query_service.CANDIDATE_WRITEBACK_EXPLANATION,
                ),
            ],
        ),
    )
    save_session(
        settings,
        session,
        request_id="req-replay-owner-guard-01",
        idempotency_key="idem-replay-owner-guard",
        details=session.replay_intent,
    )
    begin_mutation_request(
        settings,
        entity_type="query",
        entity_id=session.session_id,
        action=query_service.QUERY_MUTATION_ACTION,
        idempotency_key="idem-replay-owner-guard",
        actor_role=ActorRole.STUDENT.value,
        actor_id=session.user_id,
        request_fingerprint="fingerprint-replay-owner-guard",
        created_at=created_at,
    )
    mismatched_response = query_service.QueryResponse(
        answer=session.answer,
        answer_basis=["formal_wiki"],
        retrieval_refs=[],
        writeback_plan=[
            query_service.WritebackPlanItem(
                kind="session",
                action="save",
                status="registered",
                target_id=session.session_id,
                explanation=query_service.SESSION_WRITEBACK_EXPLANATION,
            ),
            query_service.WritebackPlanItem(
                kind="learning_note",
                action="update",
                status="updated",
                target_id=learning_proposal.learning_note_id,
                explanation=query_service.LEARNING_WRITEBACK_EXPLANATION,
            ),
            query_service.WritebackPlanItem(
                kind="candidate",
                action="create",
                status="open",
                target_id="cand-replay-owner-guard-other",
                explanation=query_service.CANDIDATE_WRITEBACK_EXPLANATION,
            ),
        ],
        session_id=session.session_id,
        created_at=created_at,
    )
    store_mutation_request_response_payload(
        settings,
        entity_type="query",
        entity_id=session.session_id,
        action=query_service.QUERY_MUTATION_ACTION,
        idempotency_key="idem-replay-owner-guard",
        updated_at=created_at,
        response_payload=mismatched_response.model_dump(mode="json", exclude_none=True),
    )
    mutation_request = next(
        record
        for record in list_mutation_requests(settings, entity_type="query")
        if record.entity_id == session.session_id
        and record.idempotency_key == "idem-replay-owner-guard"
    )
    repair_calls = {"count": 0}

    def capture_repair(*args, **kwargs):
        repair_calls["count"] += 1
        return session

    monkeypatch.setattr(query_service, "_attempt_replay_artifact_ref_repair", capture_repair)

    loaded = query_service._load_replayed_query_response(
        mutation_request,
        settings=settings,
        session_id=session.session_id,
        request_id="req-replay-owner-guard-02",
        idempotency_key="idem-replay-owner-guard",
    )

    assert loaded is None
    assert repair_calls["count"] == 0


def test_load_replayed_query_response_requires_durable_session_state(
    tmp_path: Path,
) -> None:
    _client, settings = build_client(tmp_path)
    created_at = _parse_timestamp("2026-04-10T12:09:00Z")
    begin_mutation_request(
        settings,
        entity_type="query",
        entity_id="ses-replay-missing-session",
        action=query_service.QUERY_MUTATION_ACTION,
        idempotency_key="idem-replay-missing-session",
        actor_role=ActorRole.STUDENT.value,
        actor_id="stu-kim-minji",
        request_fingerprint="fp-replay-missing-session",
        created_at=created_at,
    )
    store_mutation_request_response_payload(
        settings,
        entity_type="query",
        entity_id="ses-replay-missing-session",
        action=query_service.QUERY_MUTATION_ACTION,
        idempotency_key="idem-replay-missing-session",
        updated_at=created_at,
        response_payload=query_service.QueryResponse(
            answer="LLM decorated answer that must not become replay truth.",
            answer_basis=["formal_wiki"],
            retrieval_refs=[],
            writeback_plan=[
                query_service.WritebackPlanItem(
                    kind="session",
                    action="save",
                    status="registered",
                    target_id="ses-replay-missing-session",
                    explanation=query_service.SESSION_WRITEBACK_EXPLANATION,
                )
            ],
            session_id="ses-replay-missing-session",
            created_at=created_at,
        ).model_dump(mode="json", exclude_none=True),
    )
    mutation_request = next(
        record
        for record in list_mutation_requests(settings, entity_type="query")
        if record.entity_id == "ses-replay-missing-session"
        and record.idempotency_key == "idem-replay-missing-session"
    )

    loaded = query_service._load_replayed_query_response(
        mutation_request,
        settings=settings,
        session_id="ses-replay-missing-session",
        request_id="req-replay-missing-session",
        idempotency_key="idem-replay-missing-session",
    )

    assert loaded is None


def test_load_replayed_query_response_reprojects_deterministic_payload_from_session_state(
    tmp_path: Path,
) -> None:
    _client, settings = build_client(tmp_path)
    created_at = _parse_timestamp("2026-04-10T12:09:30Z")
    session = SessionRecord(
        session_id="ses-replay-answer-drift",
        role=ActorRole.STUDENT,
        user_id="stu-kim-minji",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        question="When is the chain rule different from the product rule?",
        answer="Use the chain rule for nested functions, then multiply by the inner derivative.",
        created_at=created_at,
        tags=["misconception"],
        retrieval_refs=[
            {
                "entity_type": "wiki_page",
                "entity_id": "page-misconceptions-chain-rule-product-rule",
                "reason": "matched concept page",
                "source_refs": [],
            }
        ],
    )
    save_session(
        settings,
        session,
        request_id="req-replay-answer-drift-seed",
        idempotency_key="idem-replay-answer-drift",
        details=None,
    )
    durable_response = query_service.QueryResponse(
        answer=session.answer,
        answer_basis=["formal_wiki"],
        retrieval_refs=[
            query_service.RetrievalRef(
                entity_type="wiki_page",
                entity_id="page-misconceptions-chain-rule-product-rule",
                reason="matched concept page",
                source_refs=[],
            )
        ],
        writeback_plan=[
            query_service.WritebackPlanItem(
                kind="session",
                action="save",
                status="registered",
                target_id=session.session_id,
                explanation=query_service.SESSION_WRITEBACK_EXPLANATION,
            ),
            query_service.WritebackPlanItem(
                kind="learning_note",
                action="update",
                status="generated",
                target_id="learn-stu-kim-minji-course-calculus-1-class-calculus-1-2026-spring-a",
                explanation=query_service.LEARNING_WRITEBACK_EXPLANATION,
            ),
        ],
        session_id=session.session_id,
        created_at=created_at,
    )
    session = query_service._persist_query_replay_intent(
        settings,
        session=session,
        response=durable_response,
        answer_basis=durable_response.answer_basis,
        idempotency_key="idem-replay-answer-drift",
        learning_proposal=None,
        candidate_proposal=None,
    )
    begin_mutation_request(
        settings,
        entity_type="query",
        entity_id=session.session_id,
        action=query_service.QUERY_MUTATION_ACTION,
        idempotency_key="idem-replay-answer-drift",
        actor_role=ActorRole.STUDENT.value,
        actor_id="stu-kim-minji",
        request_fingerprint="fp-replay-answer-drift",
        created_at=created_at,
    )
    stale_payload = query_service.QueryResponse(
        answer="LLM decorated answer that drifted from session storage.",
        answer_basis=["raw_source_fallback"],
        retrieval_refs=[
            query_service.RetrievalRef(
                entity_type="raw_source",
                entity_id="src-drifted-raw-source",
                reason="stale provider cache",
                source_refs=[],
            )
        ],
        writeback_plan=[
            query_service.WritebackPlanItem(
                kind="session",
                action="save",
                status="registered",
                target_id=session.session_id,
                explanation=query_service.SESSION_WRITEBACK_EXPLANATION,
            ),
            query_service.WritebackPlanItem(
                kind="candidate",
                action="create",
                status="open",
                target_id="cand-drifted-cache",
                explanation=query_service.CANDIDATE_WRITEBACK_EXPLANATION,
            ),
        ],
        session_id=session.session_id,
        created_at=created_at,
    ).model_dump(mode="json", exclude_none=True)
    mark_mutation_request_applied(
        settings,
        entity_type="query",
        entity_id=session.session_id,
        action=query_service.QUERY_MUTATION_ACTION,
        idempotency_key="idem-replay-answer-drift",
        updated_at=created_at,
        response_payload=stale_payload,
    )
    mutation_request = next(
        record
        for record in list_mutation_requests(settings, entity_type="query")
        if record.entity_id == session.session_id
        and record.idempotency_key == "idem-replay-answer-drift"
    )

    loaded = query_service._load_replayed_query_response(
        mutation_request,
        settings=settings,
        session_id=session.session_id,
        request_id="req-replay-answer-drift-retry",
        idempotency_key="idem-replay-answer-drift",
    )

    assert loaded is not None
    assert loaded.model_dump(mode="json") == durable_response.model_dump(mode="json")
    refreshed_mutation = next(
        record
        for record in list_mutation_requests(settings, entity_type="query")
        if record.entity_id == session.session_id
        and record.idempotency_key == "idem-replay-answer-drift"
    )
    assert refreshed_mutation.response_payload == durable_response.model_dump(
        mode="json",
        exclude_none=True,
    )
    drift_audits = [
        event
        for event in list_audit_events(settings, request_id="req-replay-answer-drift-retry")
        if event.action == "query_replay_payload_drift_detected"
    ]
    assert len(drift_audits) == 1
    assert drift_audits[0].details["drift_fields"] == [
        "answer",
        "answer_basis",
        "retrieval_refs",
        "writeback_plan",
    ]


def test_recover_candidate_writeback_item_uses_proposed_candidate_id_from_upsert_audit(
    tmp_path: Path,
) -> None:
    _client, settings = build_client(tmp_path)
    session = SessionRecord(
        session_id="ses-replay-candidate-upsert",
        role=ActorRole.STUDENT,
        user_id="stu-kim-minji",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        question=(
            "I still do not understand when the chain rule is different "
            "from the product rule."
        ),
        answer="Use the inner function derivative first.",
        created_at=_parse_timestamp("2026-04-10T12:10:00Z"),
        tags=["misconception"],
    )
    candidate_proposal = query_service.CandidateItem(
        candidate_id="cand-proposed-replay-upsert",
        kind=CandidateKind.MISCONCEPTION,
        status=CandidateStatus.OPEN,
        title="Students confuse the chain rule with the product rule",
        summary="Student mixed chain rule and product rule steps.",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        confidence=0.9,
        tags=["chain-rule"],
        source_refs=[
            query_service.SourceRef(
                source_id="src-lecture-chain-rule",
                source_type=SourceType.LECTURE_NOTE,
                chunk_id=None,
            )
        ],
        session_refs=[session.session_id],
        created_at=session.created_at,
        updated_at=session.created_at,
        related_page_id="page-misconceptions-chain-rule-product-rule",
    )
    upsert_event = create_audit_event(
        settings,
        entity_type="candidate",
        entity_id="cand-existing-open",
        action="candidate_signal_upserted",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-query-engine",
        request_id="req-replay-candidate-upsert",
        idempotency_key="idem-replay-candidate-upsert",
        details={
            "proposed_candidate_id": candidate_proposal.candidate_id,
            "target_id": "cand-existing-open",
        },
        created_at=_parse_timestamp("2026-04-10T12:10:01Z"),
    )

    recovered_item = query_service._recover_candidate_writeback_item(
        settings,
        session=session,
        request_audits=[upsert_event],
        candidate_proposal=candidate_proposal,
    )

    assert recovered_item is not None
    assert recovered_item.action == "update"
    assert recovered_item.status == "updated"
    assert recovered_item.target_id == "cand-existing-open"


@pytest.mark.parametrize(
    "fixture_name",
    QUERY_FIXTURE_NAMES,
)
@pytest.mark.smoke
def test_query_endpoint_matches_fixture_expectations(
    tmp_path: Path,
    fixture_name: str,
) -> None:
    client, settings = build_client(tmp_path)
    source_id_map = seed_query_runtime(settings)
    fixture = _load_query_fixture(fixture_name)
    _assert_query_fixture(
        client,
        settings,
        fixture,
        source_id_map=source_id_map,
    )


@pytest.mark.parametrize("fixture_name", QUERY_ERROR_FIXTURE_NAMES)
def test_query_endpoint_matches_declarative_error_fixtures(
    tmp_path: Path,
    fixture_name: str,
) -> None:
    client, settings = build_client(tmp_path)
    source_id_map = seed_query_runtime(settings)
    fixture = _load_query_fixture(fixture_name)
    _assert_query_fixture(
        client,
        settings,
        fixture,
        source_id_map=source_id_map,
    )


def test_query_endpoint_llm_rewrite_keeps_non_answer_contract_artifacts_stable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _load_query_fixture("student-chain-rule-confusion.json")
    fixed_now = _parse_timestamp("2026-04-11T01:02:03.456789Z")
    original_datetime = query_service.datetime

    class FixedDateTime(original_datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now
            return fixed_now.astimezone(tz)

    def canonicalize(data: dict[str, object]) -> dict[str, object]:
        normalized = deepcopy(data)
        normalized.pop("answer", None)
        return normalized

    monkeypatch.setattr(query_service, "datetime", FixedDateTime)

    baseline_client, baseline_settings = build_client(tmp_path / "baseline")
    baseline_source_ids = seed_query_runtime(baseline_settings)
    baseline_response = _run_query_fixture_request(
        baseline_client,
        fixture,
        source_id_map=baseline_source_ids,
    )
    assert baseline_response.status_code == 200
    baseline_payload = baseline_response.json()
    assert baseline_payload["meta"]["runtime"] == {
        "answer_source": "deterministic_fallback",
        "stored_answer_source": "deterministic_fallback",
        "llm_enabled": False,
        "llm_applied": False,
        "provider": None,
        "configured_model": None,
    }

    monkeypatch.setattr(
        query_service,
        "generate_grounded_answer",
        lambda _settings, *, context: (
            "Use the chain rule when one function is nested inside another, "
            "and compare it with a side-by-side product rule example."
        ),
    )

    llm_client, llm_settings = build_client(
        tmp_path / "llm",
        llm_enabled=True,
        openai_api_key="test-key",
    )
    llm_source_ids = seed_query_runtime(llm_settings)
    llm_response = _run_query_fixture_request(
        llm_client,
        fixture,
        source_id_map=llm_source_ids,
    )
    assert llm_response.status_code == 200
    llm_payload = llm_response.json()
    assert llm_payload["meta"]["runtime"] == {
        "answer_source": "llm_rewrite",
        "stored_answer_source": "deterministic_fallback",
        "llm_enabled": True,
        "llm_applied": True,
        "provider": "openai",
        "configured_model": "gpt-5.4",
    }

    assert llm_payload["data"]["answer"] != baseline_payload["data"]["answer"]
    assert canonicalize(llm_payload["data"]) == canonicalize(baseline_payload["data"])

    stored_session = get_session(llm_settings, llm_payload["data"]["session_id"])
    assert stored_session.answer == baseline_payload["data"]["answer"]


def test_query_endpoint_llm_rewrite_keeps_replay_payload_deterministic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = deepcopy(_load_query_fixture("student-chain-rule-confusion.json"))
    fixture["request_headers"]["Idempotency-Key"] = "idem-query-llm-durable-01"

    monkeypatch.setattr(
        query_service,
        "generate_grounded_answer",
        lambda _settings, *, context: (
            "Use the chain rule when one function is nested inside another, "
            "and compare it with a side-by-side product rule example."
        ),
    )

    client, settings = build_client(
        tmp_path,
        llm_enabled=True,
        openai_api_key="test-key",
    )
    source_ids = seed_query_runtime(settings)

    first = _run_query_fixture_request(
        client,
        fixture,
        source_id_map=source_ids,
    )
    assert first.status_code == 200
    first_payload = first.json()["data"]
    stored_session = get_session(settings, first_payload["session_id"])
    assert stored_session.answer != first_payload["answer"]

    _assert_query_mutation_request_cached(
        settings,
        session_id=first_payload["session_id"],
        idempotency_key=fixture["request_headers"]["Idempotency-Key"],
        response_payload={
            **first_payload,
            "answer": stored_session.answer,
        },
    )

    second_headers = {
        **fixture["request_headers"],
        "X-Request-Id": "req-query-llm-durable-02",
    }
    second = client.post(
        "/api/v1/query/respond",
        headers=second_headers,
        json=_resolve_query_request_body(
            fixture["request_body"],
            source_id_map=source_ids,
        ),
    )
    assert second.status_code == 200
    assert second.json()["data"]["answer"] == stored_session.answer


def test_query_endpoint_llm_guard_falls_back_without_contract_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("KNOWLOOP_ALLOW_LIVE_LLM_IN_TESTS", "true")
    fixture = _load_query_fixture("student-chain-rule-confusion.json")
    fixed_now = _parse_timestamp("2026-04-11T01:02:03.456789Z")
    original_datetime = query_service.datetime

    class FixedDateTime(original_datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now
            return fixed_now.astimezone(tz)

    def canonicalize(data: dict[str, object]) -> dict[str, object]:
        return deepcopy(data)

    class FakeResponses:
        def parse(self, **kwargs):  # noqa: ANN003
            class Response:
                output_parsed = type(
                    "ParsedPayload",
                    (),
                    {
                        "rewritten_text": (
                            "See src-lecture-note-week-03 at C:\\data\\wiki\\formal.md."
                        )
                    },
                )()

            return Response()

    class FakeClient:
        def __init__(self, *, api_key: str, timeout: float) -> None:
            self.responses = FakeResponses()

    monkeypatch.setattr(query_service, "datetime", FixedDateTime)

    baseline_client, baseline_settings = build_client(tmp_path / "baseline")
    baseline_source_ids = seed_query_runtime(baseline_settings)
    baseline_response = _run_query_fixture_request(
        baseline_client,
        fixture,
        source_id_map=baseline_source_ids,
    )
    assert baseline_response.status_code == 200
    baseline_payload = baseline_response.json()

    monkeypatch.setattr("knowloop_api.services.llm_runtime.OpenAI", FakeClient)

    llm_client, llm_settings = build_client(
        tmp_path / "llm",
        llm_enabled=True,
        openai_api_key="test-key",
    )
    llm_source_ids = seed_query_runtime(llm_settings)
    llm_response = _run_query_fixture_request(
        llm_client,
        fixture,
        source_id_map=llm_source_ids,
    )
    assert llm_response.status_code == 200
    llm_payload = llm_response.json()
    assert llm_payload["meta"]["runtime"] == {
        "answer_source": "deterministic_fallback",
        "stored_answer_source": "deterministic_fallback",
        "llm_enabled": True,
        "llm_applied": False,
        "provider": "openai",
        "configured_model": "gpt-5.4",
    }

    assert canonicalize(llm_payload["data"]) == canonicalize(baseline_payload["data"])


def test_query_build_answer_uses_fallback_when_live_provider_output_is_rejected(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("KNOWLOOP_ALLOW_LIVE_LLM_IN_TESTS", "true")

    class FakeResponses:
        def parse(self, **kwargs):  # noqa: ANN003
            class Response:
                output_parsed = {
                    "rewritten_text": "See src-lecture-note-week-03 at C:\\data\\wiki\\formal.md."
                }

            return Response()

    class FakeClient:
        def __init__(self, *, api_key: str, timeout: float) -> None:
            self.responses = FakeResponses()

    monkeypatch.setattr("knowloop_api.services.llm_runtime.OpenAI", FakeClient)

    _client, settings = build_client(
        tmp_path / "llm-build-answer",
        llm_enabled=True,
        openai_api_key="test-key",
    )
    seed_query_runtime(settings)
    context = RequestContext(
        role=ActorRole.STUDENT,
        actor_id="stu-kim-minji",
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        domain=RequestDomain.ACADEMIC,
        request_id="req-query-llm-build-answer-01",
        idempotency_key=None,
    )
    request = query_service.QueryRequest(
        message="When should I use the chain rule instead of the product rule?",
        allow_raw_source_fallback=True,
        response_mode="teaching",
    )
    tokens = query_service._tokenize(request.message)
    session_matches = list_recent_sessions(
        settings,
        user_id=context.actor_id,
        class_id=context.class_id,
        course_id=context.course_id,
        limit=5,
    )
    wiki_matches = query_service.search_wiki_pages(
        settings,
        role=context.role,
        course_id=context.course_id,
        class_id=context.class_id,
        requested_domain=context.domain,
        message=request.message,
        limit=5,
    )
    top_wiki_match = wiki_matches[0] if wiki_matches else None
    raw_source_hits = query_service._collect_raw_source_hits(
        settings,
        context=context,
        request=request,
        tokens=tokens,
        recent_sessions=session_matches,
        top_wiki_match=top_wiki_match,
    )
    learning_note = get_learning_note(
        settings,
        student_id=context.actor_id,
        course_id=context.course_id,
        class_id=context.class_id,
    )
    answer_basis = query_service._build_answer_basis(
        context=context,
        request=request,
        session_matches=session_matches,
        top_wiki_match=top_wiki_match,
        raw_source_hits=raw_source_hits,
        learning_note=learning_note,
        candidate_kind=None,
    )

    built_answer = query_service._build_answer(
        settings,
        request=request,
        context=context,
        top_wiki_match=top_wiki_match,
        raw_source_hits=raw_source_hits,
        answer_basis=answer_basis,
        learning_note=learning_note,
        session_matches=session_matches,
    )
    expected_fallback = query_service._build_fallback_answer(
        request=request,
        context=context,
        top_wiki_match=top_wiki_match,
        raw_source_hits=raw_source_hits,
        answer_basis=answer_basis,
        learning_note=learning_note,
    )

    assert built_answer.response_answer == expected_fallback
    assert built_answer.stored_answer == expected_fallback


def test_query_build_answer_prefers_llm_output_when_enabled(monkeypatch, tmp_path: Path) -> None:
    _client, settings = build_client(
        tmp_path / "llm-prefers-runtime",
        llm_enabled=True,
        openai_api_key="test-key",
    )
    context = RequestContext(
        role=ActorRole.STUDENT,
        actor_id="stu-kim-minji",
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        domain=RequestDomain.ACADEMIC,
        request_id="req-llm-answer-01",
        idempotency_key=None,
    )
    request = query_service.QueryRequest(
        message="When do I use the chain rule?",
        attachment_source_ids=[],
        allow_raw_source_fallback=False,
        response_mode="teaching",
    )

    monkeypatch.setattr(
        query_service,
        "generate_grounded_answer",
        lambda _settings, *, context: (
            "Use the chain rule when one function is nested inside another."
        ),
    )

    answer = query_service._build_answer(
        settings,
        request=request,
        context=context,
        top_wiki_match=None,
        raw_source_hits=[],
        answer_basis=["formal_wiki"],
        learning_note=None,
        session_matches=[],
    )

    assert (
        answer.response_answer
        == "Use the chain rule when one function is nested inside another."
    )
    assert answer.stored_answer != answer.response_answer
    assert "product rule" in answer.stored_answer


def test_query_build_answer_falls_back_when_llm_runtime_returns_none(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _client, settings = build_client(
        tmp_path / "llm-fallback-runtime",
        llm_enabled=True,
        openai_api_key="test-key",
    )
    context = RequestContext(
        role=ActorRole.STUDENT,
        actor_id="stu-kim-minji",
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        domain=RequestDomain.ACADEMIC,
        request_id="req-llm-answer-02",
        idempotency_key=None,
    )
    request = query_service.QueryRequest(
        message="When do I use the chain rule?",
        attachment_source_ids=[],
        allow_raw_source_fallback=False,
        response_mode="teaching",
    )

    monkeypatch.setattr(
        query_service,
        "generate_grounded_answer",
        lambda _settings, *, context: None,
    )

    answer = query_service._build_answer(
        settings,
        request=request,
        context=context,
        top_wiki_match=None,
        raw_source_hits=[],
        answer_basis=["formal_wiki"],
        learning_note=None,
        session_matches=[],
    )

    assert answer.response_answer == answer.stored_answer
    assert "Use the chain rule when one function is nested inside another" in answer.response_answer


def test_query_builds_minimized_llm_evidence_blocks(tmp_path: Path) -> None:
    _client, settings = build_client(tmp_path)
    seed_query_runtime(settings)
    context = RequestContext(
        role=ActorRole.STUDENT,
        actor_id="stu-kim-minji",
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        domain=RequestDomain.ACADEMIC,
        request_id="req-query-llm-evidence-01",
        idempotency_key=None,
    )
    request = query_service.QueryRequest(
        message=(
            "I still do not understand when the chain rule is different "
            "from the product rule."
        ),
        attachment_source_ids=[],
        allow_raw_source_fallback=True,
        response_mode="teaching",
    )
    tokens = query_service._tokenize(request.message)
    recent_sessions = list_recent_sessions(
        settings,
        user_id=context.actor_id,
        class_id=context.class_id,
        course_id=context.course_id,
        limit=5,
    )
    wiki_matches = query_service.search_wiki_pages(
        settings,
        role=context.role,
        course_id=context.course_id,
        class_id=context.class_id,
        requested_domain=context.domain,
        message=request.message,
        limit=5,
    )
    raw_source_hits = query_service._collect_raw_source_hits(
        settings,
        context=context,
        request=request,
        tokens=tokens,
        recent_sessions=recent_sessions,
        top_wiki_match=wiki_matches[0] if wiki_matches else None,
    )
    learning_note = get_learning_note(
        settings,
        student_id=context.actor_id,
        course_id=context.course_id,
        class_id=context.class_id,
    )

    evidence_blocks = query_service._build_llm_evidence_blocks(
        context=context,
        answer_basis=[
            "formal_wiki",
            "session_context",
            "learning_context",
            "raw_source_fallback",
        ],
        top_wiki_match=wiki_matches[0] if wiki_matches else None,
        raw_source_hits=raw_source_hits,
        session_matches=recent_sessions,
        learning_note=learning_note,
    )

    wiki_block = next(block for block in evidence_blocks if block.label == "formal_wiki")
    assert all("Path:" not in line for line in wiki_block.lines)
    assert all("Source refs:" not in line for line in wiki_block.lines)
    assert all(line.startswith(("Title: ", "Summary: ")) for line in wiki_block.lines)
    assert "raw_source_metadata" not in {block.label for block in evidence_blocks}
    assert all(line.startswith("- Prior topic:") for line in next(
        block for block in evidence_blocks if block.label == "session_context_summary"
    ).lines)
    learning_block = next(
        (block for block in evidence_blocks if block.label == "learning_context"),
        None,
    )
    if learning_block is not None:
        assert all(
            line.startswith(("Summary: ", "Gaps: ", "Next actions: "))
            for line in learning_block.lines
        )

    instructor_context = RequestContext(
        role=ActorRole.INSTRUCTOR,
        actor_id="ins-prof-lee",
        course_id=context.course_id,
        class_id=context.class_id,
        domain=context.domain,
        request_id="req-query-llm-evidence-02",
        idempotency_key=None,
    )
    instructor_blocks = query_service._build_llm_evidence_blocks(
        context=instructor_context,
        answer_basis=[
            "formal_wiki",
            "session_context",
            "learning_context",
            "raw_source_fallback",
        ],
        top_wiki_match=wiki_matches[0] if wiki_matches else None,
        raw_source_hits=raw_source_hits,
        session_matches=recent_sessions,
        learning_note=learning_note,
    )
    raw_block = next(
        block for block in instructor_blocks if block.label == "raw_source_metadata"
    )
    assert all(line.startswith("Reference ") and " type: " in line for line in raw_block.lines)
    assert all("src-" not in line for line in raw_block.lines)
    assert all("\\" not in line and "/" not in line for line in raw_block.lines)
    assert all("submitted by" not in line.lower() for line in raw_block.lines)

    gated_blocks = query_service._build_llm_evidence_blocks(
        context=context,
        answer_basis=["formal_wiki"],
        top_wiki_match=wiki_matches[0] if wiki_matches else None,
        raw_source_hits=raw_source_hits,
        session_matches=recent_sessions,
        learning_note=learning_note,
    )
    assert [block.label for block in gated_blocks] == ["formal_wiki"]


def test_query_session_context_evidence_ignores_storage_tags(tmp_path: Path) -> None:
    _client, _settings = build_client(tmp_path)
    session = SessionRecord(
        session_id="ses-student-stu-kim-minji-class-calculus-1-2026-spring-a-llm-tags",
        role=ActorRole.STUDENT,
        user_id="stu-kim-minji",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        question="When is the chain rule different from the product rule in nested functions?",
        answer="Use the outer derivative first, then multiply by the inner derivative.",
        created_at=_parse_timestamp("2026-04-11T02:03:04Z"),
        tags=["academic", "misconception", "faq", "chain-rule"],
        source_refs=[],
        retrieval_refs=[],
        candidate_refs=[],
        learning_note_refs=[],
        replay_intent=None,
    )

    block = query_service._build_session_evidence_block([session])

    assert block == query_service.EvidenceBlock(
        label="session_context_summary",
        lines=(
            "- Prior topic: When is the chain rule different from the product rule in "
            "nested functions",
        ),
    )


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
    payload = response.json()
    assert payload["request_id"]
    assert response.headers["X-Request-Id"] == payload["request_id"]
    assert payload["error"]["code"] == "validation_failed"


def test_query_endpoint_recovers_pending_idempotent_query_without_stored_response(
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
        "Idempotency-Key": "idem-query-recovery-missing-response",
    }
    body = {
        "message": (
            "I still do not understand when the chain rule is different "
            "from the product rule."
        ),
        "attachment_source_ids": [],
        "allow_raw_source_fallback": True,
        "response_mode": "teaching",
    }

    first = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-recovery-missing-response-01"},
        json=body,
    )

    assert first.status_code == 200
    session_id = first.json()["data"]["session_id"]
    _clear_stored_query_response_payload(
        settings,
        session_id=session_id,
        idempotency_key=headers["Idempotency-Key"],
    )

    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-recovery-missing-response-02"},
        json=body,
    )

    assert second.status_code == 200
    assert second.json()["data"] == first.json()["data"]


def test_query_endpoint_replay_keeps_original_candidate_writeback_after_later_promotion(
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
        "Idempotency-Key": "idem-query-replay-after-promotion",
    }
    body = {
        "message": (
            "I still do not understand when the chain rule is different "
            "from the product rule."
        ),
        "attachment_source_ids": [],
        "allow_raw_source_fallback": True,
        "response_mode": "teaching",
    }

    first = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-replay-after-promotion-01"},
        json=body,
    )

    assert first.status_code == 200
    candidate_item = next(
        item for item in first.json()["data"]["writeback_plan"] if item["kind"] == "candidate"
    )
    assert candidate_item["status"] == "open"

    promote_candidate(
        settings,
        candidate_item["target_id"],
        approved_by="val-course-admin",
        actor_role=ActorRole.VALIDATOR,
        actor_id="val-course-admin",
        request_id="req-promote-after-query-replay",
        idempotency_key="idem-promote-after-query-replay",
    )

    _clear_stored_query_response_payload(
        settings,
        session_id=first.json()["data"]["session_id"],
        idempotency_key=headers["Idempotency-Key"],
    )
    replay = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-replay-after-promotion-02"},
        json=body,
    )

    assert replay.status_code == 200
    assert replay.json()["data"] == first.json()["data"]


def test_query_endpoint_falls_back_to_session_saved_audit_when_replay_intent_drifts(
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
        "Idempotency-Key": "idem-query-replay-intent-fallback",
    }
    body = {
        "message": (
            "I still do not understand when the chain rule is different "
            "from the product rule."
        ),
        "attachment_source_ids": [],
        "allow_raw_source_fallback": True,
        "response_mode": "teaching",
    }

    first = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-replay-intent-fallback-01"},
        json=body,
    )

    assert first.status_code == 200
    session_id = first.json()["data"]["session_id"]
    _clear_stored_query_response_payload(
        settings,
        session_id=session_id,
        idempotency_key=headers["Idempotency-Key"],
    )
    with sqlite3.connect(settings.sessions_db_path) as connection:
        connection.execute(
            """
            UPDATE sessions
            SET replay_intent_json = ?
            WHERE session_id = ?
            """,
            (
                json.dumps(
                    {
                        "contract_version": 999,
                        "answer_basis": ["formal_wiki"],
                        "candidate_proposal": {"candidate_id": 123},
                    }
                ),
                session_id,
            ),
        )
        connection.commit()

    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-replay-intent-fallback-02"},
        json=body,
    )

    assert second.status_code == 200
    assert second.json()["data"] == first.json()["data"]


def test_query_endpoint_recovers_pending_raw_fallback_query_without_stored_response(
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
        "Idempotency-Key": "idem-query-recovery-raw-fallback",
    }
    body = {
        "message": "Can the substitution method always be used for every integral in this class?",
        "attachment_source_ids": [],
        "allow_raw_source_fallback": True,
        "response_mode": "default",
    }

    first = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-recovery-raw-fallback-01"},
        json=body,
    )

    assert first.status_code == 200
    session_id = first.json()["data"]["session_id"]
    _clear_stored_query_response_payload(
        settings,
        session_id=session_id,
        idempotency_key=headers["Idempotency-Key"],
    )

    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-recovery-raw-fallback-02"},
        json=body,
    )

    assert second.status_code == 200
    assert second.json()["data"] == first.json()["data"]
    assert second.json()["data"]["answer_basis"] == ["raw_source_fallback"]


def test_query_endpoint_recovers_pending_idempotent_query_without_explicit_request_id(
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
        "Idempotency-Key": "idem-query-recovery-no-explicit-request-id",
    }
    body = {
        "message": (
            "I still do not understand when the chain rule is different "
            "from the product rule."
        ),
        "attachment_source_ids": [],
        "allow_raw_source_fallback": True,
        "response_mode": "teaching",
    }

    first = client.post("/api/v1/query/respond", headers=headers, json=body)

    assert first.status_code == 200
    session_id = first.json()["data"]["session_id"]
    _clear_stored_query_response_payload(
        settings,
        session_id=session_id,
        idempotency_key=headers["Idempotency-Key"],
    )

    second = client.post("/api/v1/query/respond", headers=headers, json=body)

    assert second.status_code == 200
    assert second.json()["data"] == first.json()["data"]


def test_query_endpoint_recovers_pending_candidate_failure_without_stored_response(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    def fail_candidate(*args, **kwargs):
        raise RuntimeError("candidate store unavailable")

    monkeypatch.setattr(query_service, "upsert_candidate_signal", fail_candidate)

    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
        "Idempotency-Key": "idem-query-recovery-candidate-failure",
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
        headers={**headers, "X-Request-Id": "req-query-recovery-candidate-failure-01"},
        json=body,
    )

    assert first.status_code == 200
    candidate_plan = next(
        item for item in first.json()["data"]["writeback_plan"] if item["kind"] == "candidate"
    )
    assert candidate_plan["status"] == "failed"
    session_id = first.json()["data"]["session_id"]
    _clear_stored_query_response_payload(
        settings,
        session_id=session_id,
        idempotency_key=headers["Idempotency-Key"],
    )

    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-recovery-candidate-failure-02"},
        json=body,
    )

    assert second.status_code == 200
    assert second.json()["data"] == first.json()["data"]


def test_query_endpoint_recovers_pending_artifact_link_failure_without_stored_response(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)
    original_update_session_artifact_refs = query_service.update_session_artifact_refs
    failure_state = {"calls": 0}

    def fail_link(*args, **kwargs):
        failure_state["calls"] += 1
        if failure_state["calls"] == 1:
            raise RuntimeError("artifact link backend unavailable")
        return original_update_session_artifact_refs(*args, **kwargs)

    monkeypatch.setattr(query_service, "update_session_artifact_refs", fail_link)

    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
        "Idempotency-Key": "idem-query-recovery-link-failure",
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
        headers={**headers, "X-Request-Id": "req-query-recovery-link-failure-01"},
        json=body,
    )

    assert first.status_code == 200
    session_id = first.json()["data"]["session_id"]
    _clear_stored_query_response_payload(
        settings,
        session_id=session_id,
        idempotency_key=headers["Idempotency-Key"],
    )

    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-recovery-link-failure-02"},
        json=body,
    )

    assert second.status_code == 200
    assert second.json()["data"] == first.json()["data"]
    repaired_session = get_session(settings, session_id)
    assert repaired_session.learning_note_refs
    assert repaired_session.candidate_refs
    assert failure_state["calls"] >= 2


def test_query_endpoint_repairs_cached_replay_artifact_links_with_stored_response(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)
    original_update_session_artifact_refs = query_service.update_session_artifact_refs
    failure_state = {"calls": 0}

    def fail_link(*args, **kwargs):
        failure_state["calls"] += 1
        if failure_state["calls"] == 1:
            raise RuntimeError("artifact link backend unavailable")
        return original_update_session_artifact_refs(*args, **kwargs)

    monkeypatch.setattr(query_service, "update_session_artifact_refs", fail_link)

    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
        "Idempotency-Key": "idem-query-replay-link-failure-cached",
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
        headers={**headers, "X-Request-Id": "req-query-replay-link-failure-cached-01"},
        json=body,
    )

    assert first.status_code == 200
    session_id = first.json()["data"]["session_id"]
    incomplete_session = get_session(settings, session_id)
    assert incomplete_session.learning_note_refs == []
    assert incomplete_session.candidate_refs == []
    pending_requests = [
        record
        for record in list_mutation_requests(settings, entity_type="query")
        if record.entity_id == session_id and record.idempotency_key == headers["Idempotency-Key"]
    ]
    assert len(pending_requests) == 1
    assert pending_requests[0].status == "pending"

    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-replay-link-failure-cached-02"},
        json=body,
    )

    assert second.status_code == 200
    assert second.json()["data"] == first.json()["data"]
    repaired_session = get_session(settings, session_id)
    assert repaired_session.learning_note_refs
    assert repaired_session.candidate_refs
    session_saved_audits = [
        event
        for event in list_audit_events(
            settings,
            entity_type="session",
            entity_id=session_id,
        )
        if event.action == "session_saved"
    ]
    assert len(session_saved_audits) == 1
    assert session_saved_audits[0].request_id == first.json()["request_id"]
    assert session_saved_audits[0].idempotency_key == headers["Idempotency-Key"]
    repaired_requests = [
        record
        for record in list_mutation_requests(settings, entity_type="query")
        if record.entity_id == session_id and record.idempotency_key == headers["Idempotency-Key"]
    ]
    assert len(repaired_requests) == 1
    assert repaired_requests[0].status == "applied"
    assert failure_state["calls"] >= 2


def test_query_endpoint_replays_cached_response_when_artifact_repair_stays_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    def fail_link(*args, **kwargs):
        raise RuntimeError("artifact link backend unavailable")

    monkeypatch.setattr(query_service, "update_session_artifact_refs", fail_link)

    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
        "Idempotency-Key": "idem-query-replay-link-failure-still-broken",
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
        headers={**headers, "X-Request-Id": "req-query-replay-link-failure-still-broken-01"},
        json=body,
    )

    assert first.status_code == 200
    session_id = first.json()["data"]["session_id"]
    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-replay-link-failure-still-broken-02"},
        json=body,
    )

    assert second.status_code == 200
    assert second.json()["data"] == first.json()["data"]
    unresolved_session = get_session(settings, session_id)
    assert unresolved_session.learning_note_refs == []
    assert unresolved_session.candidate_refs == []
    mutation_requests = [
        record
        for record in list_mutation_requests(settings, entity_type="query")
        if record.entity_id == session_id and record.idempotency_key == headers["Idempotency-Key"]
    ]
    assert len(mutation_requests) == 1
    assert mutation_requests[0].status == "pending"
    replay_request_id = second.json()["request_id"]
    replay_failure_audits = [
        event
        for event in list_audit_events(
            settings,
            request_id=replay_request_id,
        )
        if event.action == "session_artifact_link_failed"
    ]
    assert replay_failure_audits


def test_query_endpoint_reconstructs_response_when_artifact_repair_stays_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    def fail_link(*args, **kwargs):
        raise RuntimeError("artifact link backend unavailable")

    monkeypatch.setattr(query_service, "update_session_artifact_refs", fail_link)

    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
        "Idempotency-Key": "idem-query-recovery-link-failure-still-broken",
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
        headers={**headers, "X-Request-Id": "req-query-recovery-link-failure-still-broken-01"},
        json=body,
    )

    assert first.status_code == 200
    session_id = first.json()["data"]["session_id"]
    _clear_stored_query_response_payload(
        settings,
        session_id=session_id,
        idempotency_key=headers["Idempotency-Key"],
    )

    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-recovery-link-failure-still-broken-02"},
        json=body,
    )

    assert second.status_code == 200
    assert second.json()["data"] == first.json()["data"]
    unresolved_session = get_session(settings, session_id)
    assert unresolved_session.learning_note_refs == []
    assert unresolved_session.candidate_refs == []
    mutation_requests = [
        record
        for record in list_mutation_requests(settings, entity_type="query")
        if record.entity_id == session_id and record.idempotency_key == headers["Idempotency-Key"]
    ]
    assert len(mutation_requests) == 1
    assert mutation_requests[0].status == "pending"
    replay_request_id = second.json()["request_id"]
    replay_failure_audits = [
        event
        for event in list_audit_events(
            settings,
            request_id=replay_request_id,
        )
        if event.action == "session_artifact_link_failed"
    ]
    assert replay_failure_audits


def test_query_endpoint_recovers_when_identical_idempotent_request_loses_save_race(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    original_save_session = query_service.save_session
    original_load_existing_query_session = query_service._load_existing_query_session
    race_state = {"load_calls": 0, "save_calls": 0}

    def racey_load_existing_query_session(current_settings, *, session_id: str):
        race_state["load_calls"] += 1
        if race_state["load_calls"] == 1:
            return None
        return original_load_existing_query_session(current_settings, session_id=session_id)

    def racey_save_session(
        current_settings,
        session_record,
        *,
        request_id=None,
        idempotency_key=None,
        details=None,
        raise_on_existing=False,
    ):
        race_state["save_calls"] += 1
        if race_state["save_calls"] == 1:
            original_save_session(
                current_settings,
                session_record,
                request_id=request_id,
                idempotency_key=idempotency_key,
                details=details,
                raise_on_existing=False,
            )
        return original_save_session(
            current_settings,
            session_record,
            request_id=request_id,
            idempotency_key=idempotency_key,
            details=details,
            raise_on_existing=raise_on_existing,
        )

    monkeypatch.setattr(
        query_service,
        "_load_existing_query_session",
        racey_load_existing_query_session,
    )
    monkeypatch.setattr(query_service, "save_session", racey_save_session)

    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
        "X-Request-Id": "req-query-identical-idem-race-01",
        "Idempotency-Key": "idem-query-identical-race-01",
    }
    body = {
        "message": (
            "I still do not understand when the chain rule is different "
            "from the product rule."
        ),
        "attachment_source_ids": [],
        "allow_raw_source_fallback": True,
        "response_mode": "teaching",
    }

    response = client.post("/api/v1/query/respond", headers=headers, json=body)

    assert response.status_code == 200
    assert response.json()["data"]["session_id"].startswith("ses-student-stu-kim-minji-")
    assert [item["kind"] for item in response.json()["data"]["writeback_plan"]] == [
        "session",
        "learning_note",
        "candidate",
    ]
    assert race_state["save_calls"] == 1


def test_query_endpoint_race_loser_returns_durable_answer_even_when_llm_rewrites(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    original_save_session = query_service.save_session
    original_load_existing_query_session = query_service._load_existing_query_session
    race_state = {"load_calls": 0, "save_calls": 0}

    def fake_generate_grounded_answer(*args, **kwargs):
        return "LLM decorated explanation that must not survive race recovery."

    def racey_load_existing_query_session(current_settings, *, session_id: str):
        race_state["load_calls"] += 1
        if race_state["load_calls"] == 1:
            return None
        return original_load_existing_query_session(current_settings, session_id=session_id)

    def racey_save_session(
        current_settings,
        session_record,
        *,
        request_id=None,
        idempotency_key=None,
        details=None,
        raise_on_existing=False,
    ):
        race_state["save_calls"] += 1
        if race_state["save_calls"] == 1:
            original_save_session(
                current_settings,
                session_record,
                request_id=request_id,
                idempotency_key=idempotency_key,
                details=details,
                raise_on_existing=False,
            )
        return original_save_session(
            current_settings,
            session_record,
            request_id=request_id,
            idempotency_key=idempotency_key,
            details=details,
            raise_on_existing=raise_on_existing,
        )

    monkeypatch.setattr(query_service, "generate_grounded_answer", fake_generate_grounded_answer)
    monkeypatch.setattr(
        query_service,
        "_load_existing_query_session",
        racey_load_existing_query_session,
    )
    monkeypatch.setattr(query_service, "save_session", racey_save_session)

    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
        "X-Request-Id": "req-query-identical-idem-race-llm-01",
        "Idempotency-Key": "idem-query-identical-race-llm-01",
    }
    body = {
        "message": (
            "I still do not understand when the chain rule is different "
            "from the product rule."
        ),
        "attachment_source_ids": [],
        "allow_raw_source_fallback": True,
        "response_mode": "teaching",
    }

    response = client.post("/api/v1/query/respond", headers=headers, json=body)

    assert response.status_code == 200
    session_id = response.json()["data"]["session_id"]
    stored_session = get_session(settings, session_id)
    assert response.json()["data"]["answer"] == stored_session.answer
    assert response.json()["data"]["answer"] != fake_generate_grounded_answer()
    assert race_state["save_calls"] == 1


def test_query_endpoint_waits_for_delayed_race_winner_response_before_recovery(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    original_save_session = query_service.save_session
    background_done = threading.Event()
    background_errors: list[Exception] = []
    save_state = {"calls": 0}
    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
        "X-Request-Id": "req-query-delayed-race-winner-01",
        "Idempotency-Key": "idem-query-delayed-race-winner-01",
    }
    body = {
        "message": (
            "I still do not understand when the chain rule is different "
            "from the product rule."
        ),
        "attachment_source_ids": [],
        "allow_raw_source_fallback": True,
        "response_mode": "teaching",
    }

    def delayed_winner_save_session(
        current_settings,
        session_record,
        *,
        request_id=None,
        idempotency_key=None,
        details=None,
        raise_on_existing=False,
    ):
        save_state["calls"] += 1
        if save_state["calls"] != 1:
            return original_save_session(
                current_settings,
                session_record,
                request_id=request_id,
                idempotency_key=idempotency_key,
                details=details,
                raise_on_existing=raise_on_existing,
            )

        winner_answer_basis = ["raw_source_fallback"]
        winning_session_record = session_record.model_copy(
            update={
                "replay_intent": {
                    **(session_record.replay_intent or {}),
                    "answer_basis": winner_answer_basis,
                }
            }
        )
        winning_details = {
            **(details if isinstance(details, dict) else {}),
            "answer_basis": winner_answer_basis,
        }
        original_save_session(
            current_settings,
            winning_session_record,
            request_id=request_id,
            idempotency_key=idempotency_key,
            details=winning_details,
            raise_on_existing=False,
        )
        query_service.touch_mutation_request(
            current_settings,
            entity_type="query",
            entity_id=session_record.session_id,
            action=query_service.QUERY_MUTATION_ACTION,
            idempotency_key=headers["Idempotency-Key"],
            updated_at=query_service.datetime.now(query_service.UTC),
        )

        def finish_winner() -> None:
            try:
                time.sleep(0.2)
                details_payload = {
                    **(winning_details if isinstance(winning_details, dict) else {}),
                    "answer_basis": winner_answer_basis,
                }
                learning_payload = details_payload.get("learning_proposal")
                candidate_payload = details_payload.get("candidate_proposal")
                learning_proposal = (
                    query_service.LearningNote.model_validate(learning_payload)
                    if isinstance(learning_payload, dict)
                    else None
                )
                candidate_proposal = (
                    query_service.CandidateItem.model_validate(candidate_payload)
                    if isinstance(candidate_payload, dict)
                    else None
                )

                stored_learning_note_id: str | None = None
                if learning_proposal is not None:
                    stored_learning_note = query_service.upsert_learning_note(
                        current_settings,
                        learning_proposal,
                        actor_id="system-query-engine",
                        request_id=request_id,
                        notes="Delayed race winner stored the learning note.",
                    )
                    stored_learning_note_id = stored_learning_note.learning_note_id

                stored_candidate_id: str | None = None
                candidate_action = "create"
                candidate_status = "failed"
                if candidate_proposal is not None:
                    stored_candidate, candidate_action = query_service.upsert_candidate_signal(
                        current_settings,
                        candidate_proposal,
                        actor_role=ActorRole.SYSTEM,
                        actor_id="system-query-engine",
                        request_id=request_id,
                        idempotency_key=headers["Idempotency-Key"],
                        notes="Delayed race winner stored the candidate.",
                    )
                    stored_candidate_id = stored_candidate.candidate_id
                    candidate_status = (
                        stored_candidate.status.value
                        if candidate_action == "create"
                        else "updated"
                    )

                for _ in range(10):
                    query_service.touch_mutation_request(
                        current_settings,
                        entity_type="query",
                        entity_id=session_record.session_id,
                        action=query_service.QUERY_MUTATION_ACTION,
                        idempotency_key=headers["Idempotency-Key"],
                        updated_at=query_service.datetime.now(query_service.UTC),
                    )
                    time.sleep(0.25)

                if stored_learning_note_id is not None or stored_candidate_id is not None:
                    query_service.update_session_artifact_refs(
                        current_settings,
                        session_id=session_record.session_id,
                        candidate_refs=(
                            [stored_candidate_id] if stored_candidate_id is not None else []
                        ),
                        learning_note_refs=(
                            [stored_learning_note_id]
                            if stored_learning_note_id is not None
                            else []
                        ),
                    )

                response = query_service.QueryResponse(
                    answer=session_record.answer,
                    answer_basis=list(details_payload.get("answer_basis", [])),
                    retrieval_refs=[
                        query_service.RetrievalRef.model_validate(item)
                        for item in session_record.retrieval_refs
                    ],
                    writeback_plan=[
                        query_service.WritebackPlanItem(
                            kind="session",
                            action="save",
                            status="registered",
                            target_id=session_record.session_id,
                            explanation=query_service.SESSION_WRITEBACK_EXPLANATION,
                        ),
                        query_service.WritebackPlanItem(
                            kind="learning_note",
                            action="update",
                            status="updated",
                            target_id=stored_learning_note_id or "",
                            explanation=query_service.LEARNING_WRITEBACK_EXPLANATION,
                        ),
                        query_service.WritebackPlanItem(
                            kind="candidate",
                            action=candidate_action,
                            status=candidate_status,
                            target_id=stored_candidate_id or "",
                            explanation=query_service.CANDIDATE_WRITEBACK_EXPLANATION,
                        ),
                    ],
                    session_id=session_record.session_id,
                    created_at=session_record.created_at,
                )
                response_payload = response.model_dump(mode="json", exclude_none=True)
                store_mutation_request_response_payload(
                    current_settings,
                    entity_type="query",
                    entity_id=session_record.session_id,
                    action=query_service.QUERY_MUTATION_ACTION,
                    idempotency_key=headers["Idempotency-Key"],
                    updated_at=session_record.created_at,
                    response_payload=response_payload,
                )
                mark_mutation_request_applied(
                    current_settings,
                    entity_type="query",
                    entity_id=session_record.session_id,
                    action=query_service.QUERY_MUTATION_ACTION,
                    idempotency_key=headers["Idempotency-Key"],
                    updated_at=session_record.created_at,
                    response_payload=response_payload,
                )
            except Exception as exc:  # pragma: no cover - surfaced by assertion below
                background_errors.append(exc)
            finally:
                background_done.set()

        threading.Thread(target=finish_winner, daemon=True).start()
        raise FileExistsError("simulated delayed race winner")

    monkeypatch.setattr(query_service, "save_session", delayed_winner_save_session)

    started_at = time.monotonic()
    response = client.post("/api/v1/query/respond", headers=headers, json=body)
    elapsed_seconds = time.monotonic() - started_at

    assert response.status_code == 200
    assert response.json()["data"]["answer_basis"] == ["raw_source_fallback"]
    assert background_done.wait(timeout=4)
    assert background_errors == []
    assert elapsed_seconds >= query_service.QUERY_REPLAY_PENDING_GRACE_SECONDS + 1.0
    response_request_id = response.json()["request_id"]
    session_id = response.json()["data"]["session_id"]
    repaired_session = get_session(settings, session_id)
    assert repaired_session.replay_intent["answer_basis"] == ["raw_source_fallback"]
    assert repaired_session.learning_note_refs
    assert repaired_session.candidate_refs

    learning_events = [
        event
        for event in list_audit_events(
            settings,
            entity_type="learning_note",
            entity_id=repaired_session.learning_note_refs[0],
        )
        if event.action == "learning_generated"
        and event.request_id == response_request_id
    ]
    candidate_events = [
        event
        for event in list_audit_events(
            settings,
            entity_type="candidate",
            entity_id=repaired_session.candidate_refs[0],
        )
        if event.action in {"candidate_created", "candidate_signal_upserted"}
        and event.request_id == response_request_id
    ]
    assert len(learning_events) == 1
    assert len(candidate_events) == 1


def test_query_endpoint_disables_candidate_metadata_matching_during_race_recovery(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    original_save_session = query_service.save_session
    original_upsert_candidate_signal = query_service.upsert_candidate_signal
    save_calls = {"count": 0}
    captured_flags: list[bool] = []

    def racey_save_session(
        current_settings,
        session_record,
        *,
        request_id=None,
        idempotency_key=None,
        details=None,
        raise_on_existing=False,
    ):
        save_calls["count"] += 1
        if save_calls["count"] == 1:
            original_save_session(
                current_settings,
                session_record,
                request_id=request_id,
                idempotency_key=idempotency_key,
                details=details,
                raise_on_existing=False,
            )
            raise FileExistsError("simulated save race before writeback completion")
        return original_save_session(
            current_settings,
            session_record,
            request_id=request_id,
            idempotency_key=idempotency_key,
            details=details,
            raise_on_existing=raise_on_existing,
        )

    def capture_candidate_upsert(*args, **kwargs):
        captured_flags.append(kwargs["allow_match_by_metadata"])
        return original_upsert_candidate_signal(*args, **kwargs)

    monkeypatch.setattr(query_service, "save_session", racey_save_session)
    monkeypatch.setattr(query_service, "upsert_candidate_signal", capture_candidate_upsert)

    response = client.post(
        "/api/v1/query/respond",
        headers={
            "X-Knowloop-Role": "student",
            "X-Knowloop-Actor-Id": "stu-kim-minji",
            "X-Knowloop-Course-Id": "course-calculus-1",
            "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
            "X-Knowloop-Domain": "academic",
            "X-Request-Id": "req-query-race-recovery-candidate-metadata",
            "Idempotency-Key": "idem-query-race-recovery-candidate-metadata",
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
    assert captured_flags == [False]


def test_query_service_waits_for_live_winner_during_slow_learning_writeback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    seed_query_runtime(settings)

    original_upsert_learning_note = query_service.upsert_learning_note
    slow_write_started = threading.Event()
    worker_done = threading.Event()
    worker_errors: list[Exception] = []
    worker_response: dict[str, object] = {}

    request = query_service.QueryRequest(
        message=(
            "I still do not understand when the chain rule is different "
            "from the product rule."
        ),
        attachment_source_ids=[],
        allow_raw_source_fallback=True,
        response_mode="teaching",
    )
    first_context = RequestContext(
        role=ActorRole.STUDENT,
        actor_id="stu-kim-minji",
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        domain=RequestDomain.ACADEMIC,
        request_id="req-query-live-winner-01",
        idempotency_key="idem-query-live-winner-01",
    )
    replay_context = first_context.model_copy(update={"request_id": "req-query-live-winner-02"})

    def slow_learning_writeback(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        slow_write_started.set()
        time.sleep(query_service.QUERY_REPLAY_PENDING_GRACE_SECONDS + 0.3)
        return original_upsert_learning_note(*args, **kwargs)

    def run_first_request() -> None:
        try:
            worker_response["value"] = query_service.respond_to_query(
                settings,
                request,
                context=first_context,
            )
        except Exception as exc:  # pragma: no cover - asserted below
            worker_errors.append(exc)
        finally:
            worker_done.set()

    monkeypatch.setattr(query_service, "upsert_learning_note", slow_learning_writeback)

    worker = threading.Thread(target=run_first_request, daemon=True)
    worker.start()

    assert slow_write_started.wait(timeout=4)
    started_at = time.monotonic()
    replay_response = query_service.respond_to_query(
        settings,
        request,
        context=replay_context,
    )
    elapsed_seconds = time.monotonic() - started_at

    assert worker_done.wait(timeout=4)
    worker.join(timeout=1)
    assert worker_errors == []
    first_response = worker_response["value"]
    assert replay_response.model_dump(mode="json") == first_response.model_dump(mode="json")
    assert elapsed_seconds >= query_service.QUERY_REPLAY_PENDING_GRACE_SECONDS

    mutation_requests = [
        record
        for record in list_mutation_requests(settings, entity_type="query")
        if record.idempotency_key == first_context.idempotency_key
    ]
    assert len(mutation_requests) == 1
    assert mutation_requests[0].status == "applied"
    assert mutation_requests[0].response_payload == replay_response.model_dump(
        mode="json",
        exclude_none=True,
    )

    replay_request_audits = list_audit_events(
        settings,
        request_id=replay_context.request_id,
    )
    assert replay_request_audits == []


def test_query_endpoint_duplicate_action_precedes_forbidden_scope_after_existing_mutation(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    source_id_map = seed_query_runtime(settings)

    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
        "Idempotency-Key": "idem-query-conflict-before-forbidden",
    }
    base_body = {
        "message": (
            "I still do not understand when the chain rule is different "
            "from the product rule."
        ),
        "attachment_source_ids": [],
        "allow_raw_source_fallback": True,
        "response_mode": "teaching",
    }

    first = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-conflict-before-forbidden-01"},
        json=base_body,
    )
    assert first.status_code == 200

    before = _capture_query_side_effects(
        settings,
        actor_id=headers["X-Knowloop-Actor-Id"],
        course_id=headers["X-Knowloop-Course-Id"],
        class_id=headers["X-Knowloop-Class-Id"],
        role=headers["X-Knowloop-Role"],
        request_id="req-query-conflict-before-forbidden-02",
        idempotency_key=headers["Idempotency-Key"],
    )
    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-conflict-before-forbidden-02"},
        json={
            **base_body,
            "attachment_source_ids": [
                next(iter(source_id_map.values())),
            ],
        },
    )
    after = _capture_query_side_effects(
        settings,
        actor_id=headers["X-Knowloop-Actor-Id"],
        course_id=headers["X-Knowloop-Course-Id"],
        class_id=headers["X-Knowloop-Class-Id"],
        role=headers["X-Knowloop-Role"],
        request_id="req-query-conflict-before-forbidden-02",
        idempotency_key=headers["Idempotency-Key"],
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_action"
    assert after == before


def test_query_endpoint_replay_keeps_attempt_local_request_id(
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
        "Idempotency-Key": "idem-query-attempt-local-request-id-01",
    }
    body = {
        "message": (
            "I still do not understand when the chain rule is different "
            "from the product rule."
        ),
        "attachment_source_ids": [],
        "allow_raw_source_fallback": True,
        "response_mode": "teaching",
    }

    first = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-attempt-local-01"},
        json=body,
    )
    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-attempt-local-02"},
        json=body,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["request_id"]
    assert second_payload["request_id"]
    assert first_payload["request_id"] != second_payload["request_id"]
    assert first.headers["X-Request-Id"] == first_payload["request_id"]
    assert second.headers["X-Request-Id"] == second_payload["request_id"]
    assert second_payload["data"] == first_payload["data"]


def test_query_endpoint_replay_normalizes_omitted_default_domain(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    first_headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Request-Id": "req-query-domain-normalization-01",
        "Idempotency-Key": "idem-query-domain-normalization-01",
    }
    second_headers = {
        **first_headers,
        "X-Knowloop-Domain": "academic",
        "X-Request-Id": "req-query-domain-normalization-02",
    }
    body = {
        "message": (
            "I still do not understand when the chain rule is different "
            "from the product rule."
        ),
        "attachment_source_ids": [],
        "allow_raw_source_fallback": True,
        "response_mode": "teaching",
    }

    first = client.post("/api/v1/query/respond", headers=first_headers, json=body)
    second = client.post("/api/v1/query/respond", headers=second_headers, json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["request_id"]
    assert second.headers["X-Request-Id"] == second.json()["request_id"]
    assert second.json()["data"] == first.json()["data"]


def test_query_endpoint_omits_retry_after_when_storage_busy_has_no_estimate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    def raise_storage_busy(_settings, _payload, *, context):  # noqa: ANN001, ANN202
        raise query_service.QueryStorageBusyError(
            "query replay recovery is still reconciling prior storage work"
        )

    monkeypatch.setattr(query_route_module, "respond_to_query", raise_storage_busy)

    response = client.post(
        "/api/v1/query/respond",
        headers={
            "X-Knowloop-Role": "student",
            "X-Knowloop-Actor-Id": "stu-kim-minji",
            "X-Knowloop-Course-Id": "course-calculus-1",
            "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
            "X-Knowloop-Domain": "academic",
            "X-Request-Id": "req-query-storage-busy-01",
            "Idempotency-Key": "idem-query-storage-busy-01",
        },
        json={
            "message": (
                "I still do not understand when the chain rule is different "
                "from the product rule."
            ),
            "attachment_source_ids": [],
            "allow_raw_source_fallback": True,
            "response_mode": "teaching",
        },
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["request_id"]
    assert response.headers["X-Request-Id"] == payload["request_id"]
    assert "Retry-After" not in response.headers
    assert payload == {
        "request_id": payload["request_id"],
        "error": {
            "code": "storage_busy",
            "message": "query replay recovery is still reconciling prior storage work",
            "details": {},
        },
    }


def test_query_endpoint_forbids_system_role(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    response = client.post(
        "/api/v1/query/respond",
        headers={
            "X-Knowloop-Role": "system",
            "X-Knowloop-Actor-Id": "system-query-engine",
            "X-Knowloop-Course-Id": "course-calculus-1",
            "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
            "X-Knowloop-Domain": "review",
            "X-Request-Id": "req-query-system-role-01",
            "Idempotency-Key": "idem-query-system-role-01",
        },
        json={
            "message": "Summarize the current query replay contract.",
            "attachment_source_ids": [],
            "allow_raw_source_fallback": False,
            "response_mode": "review",
        },
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["request_id"]
    assert response.headers["X-Request-Id"] == payload["request_id"]
    assert payload == {
        "request_id": payload["request_id"],
        "error": {
            "code": "forbidden_role",
            "message": "System role cannot use the public query route.",
            "details": {},
        },
    }


def test_query_endpoint_recovers_repaired_learning_writeback_after_lost_replay_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)
    failure_state = {"calls": 0}
    original_upsert_learning_note = query_service.upsert_learning_note

    def fail_once_then_recover(*args, **kwargs):
        failure_state["calls"] += 1
        if failure_state["calls"] == 1:
            raise RuntimeError("learning backend unavailable")
        return original_upsert_learning_note(*args, **kwargs)

    monkeypatch.setattr(query_service, "upsert_learning_note", fail_once_then_recover)

    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
        "Idempotency-Key": "idem-query-recovery-learning-repaired",
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
        headers={**headers, "X-Request-Id": "req-query-recovery-learning-repaired-01"},
        json=body,
    )
    assert first.status_code == 200
    first_learning = next(
        item for item in first.json()["data"]["writeback_plan"] if item["kind"] == "learning_note"
    )
    assert first_learning["status"] == "failed"

    session_id = first.json()["data"]["session_id"]
    _clear_stored_query_response_payload(
        settings,
        session_id=session_id,
        idempotency_key=headers["Idempotency-Key"],
    )
    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-recovery-learning-repaired-02"},
        json=body,
    )
    assert second.status_code == 200
    second_learning = next(
        item for item in second.json()["data"]["writeback_plan"] if item["kind"] == "learning_note"
    )
    assert second_learning["status"] == "updated"

    _clear_stored_query_response_payload(
        settings,
        session_id=session_id,
        idempotency_key=headers["Idempotency-Key"],
    )
    third = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-recovery-learning-repaired-03"},
        json=body,
    )
    assert third.status_code == 200
    assert third.json()["data"] == second.json()["data"]


def test_query_endpoint_recovers_repaired_candidate_writeback_after_lost_replay_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)
    failure_state = {"calls": 0}
    original_upsert_candidate_signal = query_service.upsert_candidate_signal

    def fail_once_then_recover(*args, **kwargs):
        failure_state["calls"] += 1
        if failure_state["calls"] == 1:
            raise RuntimeError("candidate store unavailable")
        return original_upsert_candidate_signal(*args, **kwargs)

    monkeypatch.setattr(query_service, "upsert_candidate_signal", fail_once_then_recover)

    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
        "Idempotency-Key": "idem-query-recovery-candidate-repaired",
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
        headers={**headers, "X-Request-Id": "req-query-recovery-candidate-repaired-01"},
        json=body,
    )
    assert first.status_code == 200
    first_candidate = next(
        item for item in first.json()["data"]["writeback_plan"] if item["kind"] == "candidate"
    )
    assert first_candidate["status"] == "failed"

    session_id = first.json()["data"]["session_id"]
    _clear_stored_query_response_payload(
        settings,
        session_id=session_id,
        idempotency_key=headers["Idempotency-Key"],
    )
    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-recovery-candidate-repaired-02"},
        json=body,
    )
    assert second.status_code == 200
    second_candidate = next(
        item for item in second.json()["data"]["writeback_plan"] if item["kind"] == "candidate"
    )
    assert second_candidate["status"] != "failed"

    _clear_stored_query_response_payload(
        settings,
        session_id=session_id,
        idempotency_key=headers["Idempotency-Key"],
    )
    third = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-recovery-candidate-repaired-03"},
        json=body,
    )
    assert third.status_code == 200
    assert third.json()["data"] == second.json()["data"]


def test_query_endpoint_completes_pending_existing_session_before_replay(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    original_save_session = query_service.save_session
    crash_state = {"save_calls": 0}

    def crashing_save_session(
        current_settings,
        session_record,
        *,
        request_id=None,
        idempotency_key=None,
        details=None,
        raise_on_existing=False,
    ):
        crash_state["save_calls"] += 1
        saved = original_save_session(
            current_settings,
            session_record,
            request_id=request_id,
            idempotency_key=idempotency_key,
            details=details,
            raise_on_existing=raise_on_existing,
        )
        if crash_state["save_calls"] == 1:
            raise RuntimeError("crash after session save")
        return saved

    monkeypatch.setattr(query_service, "save_session", crashing_save_session)

    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
        "Idempotency-Key": "idem-query-pending-existing-session",
    }
    body = {
        "message": (
            "I still do not understand when the chain rule is different "
            "from the product rule."
        ),
        "attachment_source_ids": [],
        "allow_raw_source_fallback": True,
        "response_mode": "teaching",
    }

    first = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-pending-existing-session-01"},
        json=body,
    )
    pending_sessions = list_recent_sessions(
        settings,
        user_id="stu-kim-minji",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        limit=5,
    )
    pending_mutation_requests = [
        record
        for record in list_mutation_requests(settings, entity_type="query")
        if record.idempotency_key == headers["Idempotency-Key"]
    ]
    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-pending-existing-session-02"},
        json=body,
    )

    assert first.status_code == 500
    assert len(pending_mutation_requests) == 1
    pending_session = get_session(settings, pending_mutation_requests[0].entity_id)
    assert pending_session.session_id in {session.session_id for session in pending_sessions}
    assert isinstance(pending_session.replay_intent, dict)
    assert [item["kind"] for item in pending_session.replay_intent["writeback_plan"]] == [
        "session",
        "learning_note",
        "candidate",
    ]
    assert second.status_code == 200
    assert [item["kind"] for item in second.json()["data"]["writeback_plan"]] == [
        "session",
        "learning_note",
        "candidate",
    ]
    stored_session = get_session(settings, second.json()["data"]["session_id"])
    assert isinstance(stored_session.replay_intent, dict)
    assert stored_session.replay_intent["writeback_plan"] == second.json()["data"]["writeback_plan"]
    _assert_query_mutation_request_cached(
        settings,
        session_id=second.json()["data"]["session_id"],
        idempotency_key=headers["Idempotency-Key"],
        response_payload=second.json()["data"],
    )


def test_query_endpoint_recovers_when_session_saved_audit_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    original_save_session = query_service.save_session
    crash_state = {"save_calls": 0}

    def crashing_save_session_without_audit(
        current_settings,
        session_record,
        *,
        request_id=None,
        idempotency_key=None,
        details=None,
        raise_on_existing=False,
    ):
        crash_state["save_calls"] += 1
        saved = original_save_session(
            current_settings,
            session_record,
            request_id=request_id,
            idempotency_key=idempotency_key,
            details=details,
            raise_on_existing=raise_on_existing,
        )
        if crash_state["save_calls"] == 1:
            with sqlite3.connect(current_settings.audit_db_path) as connection:
                connection.execute(
                    """
                    DELETE FROM audit_events
                    WHERE entity_type = 'session'
                      AND entity_id = ?
                      AND action = 'session_saved'
                    """,
                    (session_record.session_id,),
                )
                connection.commit()
            raise RuntimeError("crash after session row and before durable audit")
        return saved

    monkeypatch.setattr(query_service, "save_session", crashing_save_session_without_audit)

    headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
        "Idempotency-Key": "idem-query-missing-session-audit",
    }
    body = {
        "message": (
            "I still do not understand when the chain rule is different "
            "from the product rule."
        ),
        "attachment_source_ids": [],
        "allow_raw_source_fallback": True,
        "response_mode": "teaching",
    }

    first = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-missing-session-audit-01"},
        json=body,
    )
    pending_sessions = list_recent_sessions(
        settings,
        user_id="stu-kim-minji",
        class_id="class-calculus-1-2026-spring-a",
        course_id="course-calculus-1",
        limit=5,
    )
    pending_mutation_requests = [
        record
        for record in list_mutation_requests(settings, entity_type="query")
        if record.idempotency_key == headers["Idempotency-Key"]
    ]
    second = client.post(
        "/api/v1/query/respond",
        headers={**headers, "X-Request-Id": "req-query-missing-session-audit-02"},
        json=body,
    )

    assert first.status_code == 500
    assert len(pending_mutation_requests) == 1
    pending_session = get_session(settings, pending_mutation_requests[0].entity_id)
    assert pending_session.session_id in {session.session_id for session in pending_sessions}
    assert isinstance(pending_session.replay_intent, dict)
    assert [item["kind"] for item in pending_session.replay_intent["writeback_plan"]] == [
        "session",
        "learning_note",
        "candidate",
    ]
    assert second.status_code == 200
    assert [item["kind"] for item in second.json()["data"]["writeback_plan"]] == [
        "session",
        "learning_note",
        "candidate",
    ]
    stored_session = get_session(settings, second.json()["data"]["session_id"])
    assert isinstance(stored_session.replay_intent, dict)
    assert stored_session.replay_intent["writeback_plan"] == second.json()["data"]["writeback_plan"]
    _assert_query_mutation_request_cached(
        settings,
        session_id=second.json()["data"]["session_id"],
        idempotency_key=headers["Idempotency-Key"],
        response_payload=second.json()["data"],
    )


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


def test_query_endpoint_preserves_distinct_learning_audits_for_same_second_requests(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_query_runtime(settings)

    timestamps = iter(
        [
            _parse_timestamp("2026-04-10T12:30:15.111111Z"),
            _parse_timestamp("2026-04-10T12:30:15.222222Z"),
        ]
    )
    original_datetime = query_service.datetime

    class FixedDateTime(original_datetime):
        @classmethod
        def now(cls, tz=None):
            value = next(timestamps)
            if tz is None:
                return value
            return value.astimezone(tz)

    monkeypatch.setattr(query_service, "datetime", FixedDateTime)

    request_headers = {
        "X-Knowloop-Role": "student",
        "X-Knowloop-Actor-Id": "stu-kim-minji",
        "X-Knowloop-Course-Id": "course-calculus-1",
        "X-Knowloop-Class-Id": "class-calculus-1-2026-spring-a",
        "X-Knowloop-Domain": "academic",
    }
    request_body = {
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
        headers={**request_headers, "X-Request-Id": "req-query-learning-audit-01"},
        json=request_body,
    )
    second = client.post(
        "/api/v1/query/respond",
        headers={**request_headers, "X-Request-Id": "req-query-learning-audit-02"},
        json=request_body,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_request_id = first.json()["request_id"]
    second_request_id = second.json()["request_id"]

    learning_note = get_learning_note(
        settings,
        student_id="stu-kim-minji",
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
    )
    assert learning_note is not None

    learning_events = [
        event
        for event in list_audit_events(
            settings,
            entity_type="learning_note",
            entity_id=learning_note.learning_note_id,
        )
        if event.action == "learning_generated"
        and event.request_id in {first_request_id, second_request_id}
    ]
    assert len(learning_events) == 2
    assert {event.request_id for event in learning_events} == {first_request_id, second_request_id}
    assert len({event.event_id for event in learning_events}) == 2


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
