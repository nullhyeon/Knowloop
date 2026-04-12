import hashlib
import json
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole, SourceType
from knowloop_api.core.frontmatter import parse_frontmatter_document
from knowloop_api.db.audit import (
    create_audit_event,
    get_mutation_request,
    list_audit_events,
    list_mutation_requests,
    store_mutation_request_response_payload,
)
from knowloop_api.main import create_app
from knowloop_api.services.candidates import (
    CandidateItem,
    CandidateStatus,
    WikiSyncStatus,
    build_candidate_path,
    create_candidate,
    get_candidate,
)
from knowloop_api.services.sources import (
    SourceRegistrationInput,
    register_source,
    resolve_source_path,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "data" / "fixtures"
REVIEW_SCHEMA_PATH = REPO_ROOT / "schemas" / "wiki_patch.json"


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
    request_id: str = "req-test-review",
    idempotency_key: str | None = None,
    domain: str | None = None,
) -> dict[str, str]:
    resolved_domain = domain or {
        "student": "academic",
        "instructor": "academic",
        "operator": "operations",
        "validator": "review",
        "system": "review",
    }[role]
    headers = {
        "X-Knowloop-Role": role,
        "X-Knowloop-Actor-Id": actor_id,
        "X-Knowloop-Course-Id": course_id,
        "X-Knowloop-Class-Id": class_id,
        "X-Request-Id": request_id,
        "X-Knowloop-Domain": resolved_domain,
    }
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def assert_server_owned_request_id(
    response,
    *,
    client_request_id: str | None,
) -> str:
    payload = response.json()
    request_id = payload["request_id"]
    assert isinstance(request_id, str)
    assert request_id.strip()
    assert response.headers["X-Request-Id"] == request_id
    if client_request_id is not None:
        assert request_id != client_request_id
        assert response.headers["X-Client-Request-Id"] == client_request_id
    else:
        assert "X-Client-Request-Id" not in response.headers
    return request_id


def assert_api_error_envelope(
    response,
    *,
    expected_code: str | None = None,
    expected_message: str | None = None,
    expected_details: dict[str, object] | None = None,
    client_request_id: str | None = None,
) -> str:
    request_id = assert_server_owned_request_id(
        response,
        client_request_id=client_request_id,
    )
    payload = response.json()
    assert {"request_id", "error"}.issubset(payload.keys())
    assert "detail" not in payload
    assert {"code", "message", "details"}.issubset(payload["error"].keys())
    assert isinstance(payload["error"]["code"], str)
    assert payload["error"]["code"].strip()
    if expected_code is not None:
        assert payload["error"]["code"] == expected_code
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"].strip()
    assert isinstance(payload["error"]["details"], dict)
    if expected_message is not None:
        assert payload["error"]["message"] == expected_message
    if expected_details is not None:
        assert payload["error"]["details"] == expected_details
    return request_id


def load_candidate_fixture(filename: str) -> CandidateItem:
    payload = json.loads((FIXTURE_ROOT / "candidates" / filename).read_text(encoding="utf-8"))
    return CandidateItem.model_validate(payload)


def load_review_fixture(filename: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / "reviews" / filename).read_text(encoding="utf-8"))


def seed_candidate(settings: Settings, filename: str) -> CandidateItem:
    candidate = load_candidate_fixture(filename)
    return create_candidate(
        settings,
        candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
    )


def seed_source_fixture(settings: Settings, filename: str) -> None:
    contents = (FIXTURE_ROOT / "sources" / filename).read_text(encoding="utf-8")
    metadata, body = parse_frontmatter_document(contents)
    actor_role = ActorRole(str(metadata["actor_role"]))
    actor_id = {
        ActorRole.INSTRUCTOR: "ins-calculus-team",
        ActorRole.OPERATOR: "ops-academic-office",
        ActorRole.SYSTEM: "system-seed",
        ActorRole.VALIDATOR: "val-course-admin",
    }[actor_role]
    register_source(
        settings,
        SourceRegistrationInput(
            source_type=SourceType(str(metadata["source_type"])),
            title=str(metadata["title"]),
            content=body,
            mime_type="text/markdown" if filename.endswith(".md") else "text/plain",
            filename=filename,
        ),
        course_id=str(metadata["course_id"]),
        class_id=str(metadata["class_id"]),
        actor_role=actor_role,
        actor_id=actor_id,
        created_at=datetime.fromisoformat(str(metadata["created_at"]).replace("Z", "+00:00")),
    )


def seed_wiki_fixture(
    settings: Settings,
    *,
    source_filename: str,
    target_relative_path: str,
) -> Path:
    target_path = settings.data_root / Path(target_relative_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        (FIXTURE_ROOT / "wiki" / source_filename).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return target_path


def parse_markdown_document(contents: str) -> tuple[dict[str, object], str]:
    metadata, body = parse_frontmatter_document(contents)
    return metadata, body.strip()


def as_zulu(timestamp: datetime) -> str:
    return timestamp.isoformat().replace("+00:00", "Z")


def capture_review_artifact_snapshot(
    settings: Settings,
    *,
    candidates: list[CandidateItem] | tuple[CandidateItem, ...] = (),
    wiki_contract_paths: list[str] | tuple[str, ...] = (),
) -> dict[Path, str | None]:
    snapshot: dict[Path, str | None] = {}
    for candidate in candidates:
        candidate_path = build_candidate_path(settings, candidate)
        snapshot[candidate_path] = candidate_path.read_text(encoding="utf-8")
    for contract_path in wiki_contract_paths:
        wiki_path = resolve_source_path(settings, contract_path)
        snapshot[wiki_path] = (
            wiki_path.read_text(encoding="utf-8") if wiki_path.exists() else None
        )
    return snapshot


def assert_review_artifact_snapshot_unchanged(snapshot: dict[Path, str | None]) -> None:
    for path, original_contents in snapshot.items():
        if original_contents is None:
            assert not path.exists()
            continue
        assert path.exists()
        assert path.read_text(encoding="utf-8") == original_contents


def assert_client_request_id_not_persisted(
    settings: Settings,
    *,
    candidate: CandidateItem,
    client_request_id: str,
    idempotency_key: str,
    mutation_action: str | None = None,
    wiki_contract_path: str | None = None,
    additional_candidates: list[CandidateItem] | tuple[CandidateItem, ...] = (),
    additional_wiki_contract_paths: list[str] | tuple[str, ...] = (),
    require_audit_events: bool = True,
) -> None:
    checked_candidate_ids: set[str] = set()
    for persisted_candidate in (candidate, *additional_candidates):
        if persisted_candidate.candidate_id in checked_candidate_ids:
            continue
        checked_candidate_ids.add(persisted_candidate.candidate_id)
        candidate_text = build_candidate_path(settings, persisted_candidate).read_text(
            encoding="utf-8"
        )
        assert client_request_id not in candidate_text

    wiki_contract_paths = [
        *( [wiki_contract_path] if wiki_contract_path is not None else [] ),
        *additional_wiki_contract_paths,
    ]
    checked_wiki_paths: set[str] = set()
    for contract_path in wiki_contract_paths:
        if contract_path in checked_wiki_paths:
            continue
        checked_wiki_paths.add(contract_path)
        wiki_text = resolve_source_path(settings, contract_path).read_text(encoding="utf-8")
        assert client_request_id not in wiki_text

    audit_events = list_audit_events(settings, idempotency_key=idempotency_key)
    if require_audit_events:
        assert audit_events
    for event in audit_events:
        assert event.request_id != client_request_id
        if event.notes is not None:
            assert client_request_id not in event.notes
        if event.details is not None:
            assert client_request_id not in json.dumps(event.details, sort_keys=True)

    if mutation_action is not None:
        mutation_request = get_mutation_request(
            settings,
            entity_type="candidate",
            entity_id=candidate.candidate_id,
            action=mutation_action,
            idempotency_key=idempotency_key,
        )
        assert mutation_request is not None
        assert client_request_id not in mutation_request.request_fingerprint
        if mutation_request.actor_id is not None:
            assert client_request_id not in mutation_request.actor_id
        if mutation_request.response_payload is not None:
            assert client_request_id not in json.dumps(
                mutation_request.response_payload,
                sort_keys=True,
            )


def assert_no_review_mutation_artifacts(
    settings: Settings,
    *,
    candidate_id: str,
    mutation_action: str,
    idempotency_key: str,
    artifact_snapshot: dict[Path, str | None] | None = None,
) -> None:
    mutation_requests = [
        request
        for request in list_mutation_requests(settings, entity_type="candidate")
        if request.idempotency_key == idempotency_key
    ]
    assert mutation_requests == []
    assert list_audit_events(settings, idempotency_key=idempotency_key) == []
    if artifact_snapshot is not None:
        assert_review_artifact_snapshot_unchanged(artifact_snapshot)


def test_review_candidate_list_returns_visible_candidates_for_instructor(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_candidate(settings, "open-misconception-chain-rule.json")
    seed_candidate(settings, "open-operations-refund.json")

    response = client.get(
        "/api/v1/review/candidates",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-review-list",
        ),
    )

    assert response.status_code == 200
    assert_server_owned_request_id(response, client_request_id="req-review-list")
    payload = response.json()
    assert payload["meta"]["total"] == 2
    assert {item["kind"] for item in payload["data"]} == {"faq", "misconception"}
    assert all(item["review_domain"] == "academic" for item in payload["data"])


def test_review_candidate_list_orders_by_candidate_updated_at(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    older = load_candidate_fixture("open-faq-homework-deadline.json").model_copy(
        update={
            "candidate_id": (
                "cand-faq-class-calculus-1-2026-spring-a-"
                "homework-ordering-older-20260408T103000Z"
            ),
            "created_at": datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
            "updated_at": datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
        }
    )
    newer = load_candidate_fixture("open-misconception-chain-rule.json").model_copy(
        update={
            "candidate_id": (
                "cand-misconception-class-calculus-1-2026-spring-a-"
                "ordering-newer-20260408T110000Z"
            ),
            "created_at": datetime(2026, 4, 8, 11, 0, tzinfo=UTC),
            "updated_at": datetime(2026, 4, 9, 9, 15, tzinfo=UTC),
        }
    )
    create_candidate(settings, older, actor_role=ActorRole.SYSTEM, actor_id="system-seed")
    create_candidate(settings, newer, actor_role=ActorRole.SYSTEM, actor_id="system-seed")

    response = client.get(
        "/api/v1/review/candidates",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-review-list-ordering",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert [item["candidate_id"] for item in payload[:2]] == [
        newer.candidate_id,
        older.candidate_id,
    ]


def test_review_candidate_detail_returns_audit_history_and_actions(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")

    response = client.get(
        f"/api/v1/review/candidates/{candidate.candidate_id}",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-review-detail",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["candidate"]["candidate_id"] == candidate.candidate_id
    assert payload["audit_events"][0]["action"] == "candidate_created"
    assert payload["available_actions"] == ["patch_preview", "approve", "merge", "drop"]


def test_review_candidate_detail_exposes_resume_sync_for_pending_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 500
    assert_api_error_envelope(
        first_response,
        expected_code="internal_error",
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )

    detail_response = client.get(
        f"/api/v1/review/candidates/{candidate.candidate_id}",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-review-detail-pending-sync",
        ),
    )

    assert detail_response.status_code == 200
    payload = detail_response.json()["data"]
    assert payload["candidate"]["status"] == "promoted"
    assert payload["candidate"]["wiki_sync_status"] == "pending"
    assert payload["candidate"]["promotion_attempt_id"].startswith("pat-cand-")
    assert payload["available_actions"] == ["resume_sync"]


def test_review_candidate_detail_keeps_system_read_only_for_pending_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 500
    assert_api_error_envelope(
        first_response,
        expected_code="internal_error",
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )

    detail_response = client.get(
        f"/api/v1/review/candidates/{candidate.candidate_id}",
        headers=build_headers(
            role="system",
            actor_id="system-review-observer",
            request_id="req-review-detail-system-pending-sync",
        ),
    )

    assert detail_response.status_code == 200
    payload = detail_response.json()["data"]
    assert payload["candidate"]["status"] == "promoted"
    assert payload["candidate"]["wiki_sync_status"] == "pending"
    assert payload["available_actions"] == ["patch_preview"]


def test_review_patch_preview_matches_homework_fixture_contract(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("patch-preview-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )
    expected_after_contents = (
        FIXTURE_ROOT / "wiki" / "faq-homework-submission.after.md"
    ).read_text(encoding="utf-8")
    review_schema = json.loads(REVIEW_SCHEMA_PATH.read_text(encoding="utf-8"))

    response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/patch-preview",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    jsonschema.validate(payload["patch"], review_schema)
    assert payload["patch"]["operation"] == "update"
    assert payload["patch"]["target_page_id"] == review_fixture["expected"]["target_page_id"]
    assert any("deadline" in step.lower() for step in payload["patch"]["change_plan"])
    assert any("lms" in step.lower() for step in payload["patch"]["change_plan"])

    actual_metadata, actual_body = parse_markdown_document(payload["after_markdown"])
    expected_metadata, expected_body = parse_markdown_document(expected_after_contents)

    assert actual_body == expected_body
    for key in ("page_id", "domain", "title", "course_id", "class_scope", "summary"):
        assert actual_metadata[key] == expected_metadata[key]
    assert actual_metadata["source_refs"] == expected_metadata["source_refs"]
    assert actual_metadata["candidate_refs"] == expected_metadata["candidate_refs"]
    assert actual_metadata["updated_at"]


def test_review_patch_preview_rejects_invalid_target_page_id_contract(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    candidate = seed_candidate(settings, "open-operations-refund.json")

    response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/patch-preview",
        headers=build_headers(
            role="operator",
            actor_id="ops-academic-office",
            request_id="req-review-preview-invalid-page-id",
        ),
        json={
            "target_page_id": "page-faq-homework-submission",
            "target_path": "data/wiki/operations/class-calculus-1-2026-spring-a/refund-policy.md",
            "notes": "Reject mismatched page contract for operations wiki preview.",
        },
    )

    assert response.status_code == 400
    assert_api_error_envelope(
        response,
        expected_code="invalid_request",
        client_request_id="req-review-preview-invalid-page-id",
    )


def test_review_patch_preview_rejects_target_page_id_path_traversal(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")

    response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/patch-preview",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-review-preview-path-traversal",
        ),
        json={
            "target_page_id": "page-faq-../../operations/class-calculus-1-2026-spring-a/injected",
            "notes": "Reject page_id path traversal before any wiki path is resolved.",
        },
    )

    assert response.status_code == 400
    assert_api_error_envelope(
        response,
        expected_code="invalid_request",
        client_request_id="req-review-preview-path-traversal",
    )


def test_review_patch_preview_treats_target_page_id_as_scope_local(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    cross_scope_path = (
        settings.data_root
        / "wiki"
        / "faq"
        / "class-calculus-1-2026-spring-b"
        / "homework-submission-cross-scope.md"
    )
    cross_scope_path.parent.mkdir(parents=True, exist_ok=True)
    cross_scope_path.write_text(
        """---
page_id: page-faq-homework-submission-cross-scope
domain: faq
title: Homework Submission
course_id: course-calculus-1
class_scope: class-calculus-1-2026-spring-b
updated_at: 2026-04-08T10:40:00Z
source_refs: []
candidate_refs: []
summary: A cross-scope page that must not be previewed from another class.
---

# Homework Submission

This page belongs to another class scope.
""",
        encoding="utf-8",
    )

    response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/patch-preview",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-review-preview-scope-local-page-id",
        ),
        json={
            "target_page_id": "page-faq-homework-submission-cross-scope",
            "notes": "Scope-local page IDs should resolve to the current class path.",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["patch"]["target_page_id"] == "page-faq-homework-submission-cross-scope"
    assert (
        payload["patch"]["target_path"]
        == "data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission-cross-scope.md"
    )
    assert payload["before_markdown"] is None


def test_review_patch_preview_returns_domain_error_for_malformed_canonical_wiki_page(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    malformed_path = (
        settings.data_root
        / "wiki"
        / "faq"
        / "class-calculus-1-2026-spring-a"
        / "homework-submission.md"
    )
    malformed_path.parent.mkdir(parents=True, exist_ok=True)
    malformed_path.write_text(
        """---
page_id page-faq-homework-submission
domain: faq
course_id: course-calculus-1
class_scope: class-calculus-1-2026-spring-a
---

# Homework Submission

This canonical page is malformed and should not crash the review flow.
""",
        encoding="utf-8",
    )

    response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/patch-preview",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-review-preview-malformed-canonical-page",
        ),
        json={
            "target_page_id": "page-faq-homework-submission",
            "notes": "Malformed canonical page should surface as a review error.",
        },
    )

    assert response.status_code == 400
    assert_api_error_envelope(
        response,
        expected_code="invalid_request",
        client_request_id="req-review-preview-malformed-canonical-page",
    )
    assert "could not be read" in response.json()["error"]["message"]


def test_review_approve_promotes_candidate_and_writes_wiki_page(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    written_path = seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )
    expected_after_contents = (
        FIXTURE_ROOT / "wiki" / "faq-homework-submission.after.md"
    ).read_text(encoding="utf-8")

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )
    second_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers={
            **review_fixture["request_headers"],
            "X-Request-Id": "req-fixture-approve-homework-faq-replay",
        },
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_request_id = assert_server_owned_request_id(
        first_response,
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )
    second_request_id = assert_server_owned_request_id(
        second_response,
        client_request_id="req-fixture-approve-homework-faq-replay",
    )
    assert first_request_id != second_request_id
    response_payload = first_response.json()["data"]
    stored_candidate = get_candidate(settings, candidate.candidate_id)
    assert response_payload["candidate"]["status"] == "promoted"
    assert response_payload["candidate"]["wiki_sync_status"] == "synced"
    assert stored_candidate.status is CandidateStatus.PROMOTED
    assert stored_candidate.wiki_sync_status is WikiSyncStatus.SYNCED
    assert stored_candidate.approved_by == "ins-calculus-team"
    assert response_payload["wiki_page"]["page_id"] == review_fixture["expected"]["wiki_page_id"]
    assert response_payload["wiki_page"]["updated_at"] == as_zulu(stored_candidate.wiki_synced_at)

    actual_metadata, actual_body = parse_markdown_document(written_path.read_text(encoding="utf-8"))
    expected_metadata, expected_body = parse_markdown_document(expected_after_contents)
    assert actual_body == expected_body
    assert actual_metadata["candidate_refs"] == expected_metadata["candidate_refs"]
    assert actual_metadata["source_refs"] == expected_metadata["source_refs"]

    candidate_audit = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
    )
    wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    pending_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    assert len(candidate_audit) == 1
    assert len(wiki_audit) == 1
    assert len(pending_events) == 1
    assert len(synced_events) == 1
    assert stored_candidate.wiki_synced_at == synced_events[0].created_at
    assert candidate_audit[0].created_at < pending_events[0].created_at
    assert pending_events[0].created_at < wiki_audit[0].created_at
    assert wiki_audit[0].created_at < synced_events[0].created_at
    assert_client_request_id_not_persisted(
        settings,
        candidate=stored_candidate,
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
        idempotency_key="idem-fixture-approve-homework-faq",
        mutation_action="candidate_promoted",
        wiki_contract_path=review_fixture["request_body"]["target_path"],
    )
    assert_client_request_id_not_persisted(
        settings,
        candidate=stored_candidate,
        client_request_id="req-fixture-approve-homework-faq-replay",
        idempotency_key="idem-fixture-approve-homework-faq",
        mutation_action="candidate_promoted",
        wiki_contract_path=review_fixture["request_body"]["target_path"],
    )


def test_review_approve_rejects_reused_idempotency_key_with_different_payload(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )
    second_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers={
            **review_fixture["request_headers"],
            "X-Request-Id": "req-fixture-approve-homework-faq-conflict",
        },
        json={
            **review_fixture["request_body"],
            "approval_notes": "Conflicting approval payload for the same idempotency key.",
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    first_request_id = assert_server_owned_request_id(
        first_response,
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )
    second_request_id = assert_api_error_envelope(
        second_response,
        expected_code="duplicate_action",
        client_request_id="req-fixture-approve-homework-faq-conflict",
    )
    assert first_request_id != second_request_id

    candidate_audit = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    pending_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    assert len(candidate_audit) == 1
    assert len(wiki_audit) == 1
    assert len(pending_events) == 1
    assert len(synced_events) == 1


def test_review_approve_replays_when_canonical_target_path_is_omitted_then_explicit(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json={
            "target_page_id": "page-faq-homework-submission",
            "approval_notes": review_fixture["request_body"]["approval_notes"],
        },
    )
    second_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    candidate_audit = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-approve-homework-faq",
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_request_id = assert_server_owned_request_id(
        first_response,
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )
    second_request_id = assert_server_owned_request_id(
        second_response,
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )
    assert first_request_id != second_request_id
    assert len(candidate_audit) == 1
    assert len(wiki_audit) == 1


def test_review_approve_requires_idempotency_key_at_route_boundary(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")

    response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-review-approve-no-idem",
            idempotency_key=None,
        ),
        json={
            "target_page_id": "page-faq-homework-submission",
            "target_path": "data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
            "approval_notes": "Boundary guard should reject missing idempotency.",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_review_approve_rejects_noncanonical_target_path_on_replay(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )
    second_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json={
            "target_page_id": "page-faq-homework-submission",
            "target_path": "data/wiki/faq/other-page.md",
            "approval_notes": review_fixture["request_body"]["approval_notes"],
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    first_request_id = assert_server_owned_request_id(
        first_response,
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )
    second_request_id = assert_api_error_envelope(
        second_response,
        expected_code="duplicate_action",
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )
    assert first_request_id != second_request_id


def test_review_approve_rejects_noncanonical_target_path_before_promotion(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-review-approve-invalid-target",
            idempotency_key="idem-review-approve-invalid-target",
        ),
        json={
            "target_page_id": "page-faq-homework-submission",
            "target_path": "data/wiki/faq/other-page.md",
            "approval_notes": "Reject the invalid canonical path before any candidate mutation.",
        },
    )

    stored_candidate = get_candidate(settings, candidate.candidate_id)
    promoted_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
        idempotency_key="idem-review-approve-invalid-target",
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"
    assert stored_candidate.status is CandidateStatus.OPEN
    assert promoted_events == []


def test_review_approve_recovers_after_wiki_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    written_path = seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 500
    first_failed_candidate = get_candidate(settings, candidate.candidate_id)
    assert first_failed_candidate.status is CandidateStatus.PROMOTED
    assert first_failed_candidate.wiki_sync_status is WikiSyncStatus.PENDING
    assert first_failed_candidate.wiki_synced_at is None

    second_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert second_response.status_code == 200
    recovered_candidate = get_candidate(settings, candidate.candidate_id)
    assert recovered_candidate.status is CandidateStatus.PROMOTED
    assert recovered_candidate.wiki_sync_status is WikiSyncStatus.SYNCED
    assert written_path.exists()

    pending_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-approve-homework-faq",
    )

    assert len(pending_events) == 1
    assert len(synced_events) == 1
    assert len(wiki_audit) == 1


def test_review_resume_sync_completes_pending_candidate_with_new_idempotency_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    written_path = seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )
    expected_after_contents = (
        FIXTURE_ROOT / "wiki" / "faq-homework-submission.after.md"
    ).read_text(encoding="utf-8")

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 500
    failed_candidate = get_candidate(settings, candidate.candidate_id)
    assert failed_candidate.status is CandidateStatus.PROMOTED
    assert failed_candidate.wiki_sync_status is WikiSyncStatus.PENDING
    assert failed_candidate.promotion_attempt_id is not None

    resume_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq",
            idempotency_key="idem-fixture-resume-homework-faq",
            domain="academic",
        ),
        json={"resume_notes": "Resume the frozen approval plan after the write failure."},
    )

    assert resume_response.status_code == 200
    assert_server_owned_request_id(
        resume_response,
        client_request_id="req-fixture-resume-homework-faq",
    )
    payload = resume_response.json()["data"]
    assert payload["candidate"]["status"] == "promoted"
    assert payload["candidate"]["wiki_sync_status"] == "synced"
    assert payload["candidate"]["promotion_attempt_id"] == failed_candidate.promotion_attempt_id
    assert payload["patch"]["target_page_id"] == "page-faq-homework-submission"
    assert payload["wiki_page"]["page_id"] == "page-faq-homework-submission"

    recovered_candidate = get_candidate(settings, candidate.candidate_id)
    assert recovered_candidate.status is CandidateStatus.PROMOTED
    assert recovered_candidate.wiki_sync_status is WikiSyncStatus.SYNCED
    assert recovered_candidate.promotion_attempt_id == failed_candidate.promotion_attempt_id

    final_metadata, final_body = parse_markdown_document(written_path.read_text(encoding="utf-8"))
    expected_metadata, expected_body = parse_markdown_document(expected_after_contents)
    assert final_body == expected_body
    assert final_metadata["candidate_refs"] == expected_metadata["candidate_refs"]
    assert final_metadata["source_refs"] == expected_metadata["source_refs"]

    original_pending_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    original_synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    original_wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    resumed_synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        idempotency_key="idem-fixture-resume-homework-faq",
    )
    resumed_wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-resume-homework-faq",
    )
    resumed_pending_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
        idempotency_key="idem-fixture-resume-homework-faq",
    )

    assert len(original_pending_events) == 1
    assert original_synced_events == []
    assert original_wiki_audit == []
    assert resumed_pending_events == []
    assert len(resumed_synced_events) == 1
    assert len(resumed_wiki_audit) == 1
    assert payload["wiki_page"]["updated_at"] == as_zulu(recovered_candidate.wiki_synced_at)

    replay_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-replay",
            idempotency_key="idem-fixture-resume-homework-faq",
            domain="academic",
        ),
        json={"resume_notes": "Resume the frozen approval plan after the write failure."},
    )

    assert replay_response.status_code == 200
    replay_payload = replay_response.json()["data"]
    assert replay_payload["candidate"]["candidate_id"] == candidate.candidate_id
    assert replay_payload["candidate"]["wiki_sync_status"] == "synced"
    assert replay_payload["patch"]["target_page_id"] == "page-faq-homework-submission"
    assert replay_payload["wiki_page"]["updated_at"] == as_zulu(recovered_candidate.wiki_synced_at)

    resumed_synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        idempotency_key="idem-fixture-resume-homework-faq",
    )
    resumed_wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-resume-homework-faq",
    )
    assert len(resumed_synced_events) == 1
    assert len(resumed_wiki_audit) == 1


def test_review_resume_sync_backfills_missing_pending_audit_after_approve_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_record_pending = review_service._record_candidate_wiki_sync_pending
    pending_attempts = {"count": 0}

    def flaky_record_pending(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        pending_attempts["count"] += 1
        if pending_attempts["count"] == 1:
            raise OSError("forced pending audit gap")
        return original_record_pending(*args, **kwargs)

    monkeypatch.setattr(review_service, "_record_candidate_wiki_sync_pending", flaky_record_pending)

    approve_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert approve_response.status_code == 500
    pending_candidate = get_candidate(settings, candidate.candidate_id)
    assert pending_candidate.status is CandidateStatus.PROMOTED
    assert pending_candidate.wiki_sync_status is WikiSyncStatus.PENDING

    pending_events_before_resume = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    assert pending_events_before_resume == []

    resume_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-pending-gap",
            idempotency_key="idem-fixture-resume-homework-faq-pending-gap",
            domain="academic",
        ),
        json={"resume_notes": "Resume after the pending audit marker was skipped."},
    )

    assert resume_response.status_code == 200

    backfilled_pending_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    resumed_pending_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
        idempotency_key="idem-fixture-resume-homework-faq-pending-gap",
    )
    resumed_synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        idempotency_key="idem-fixture-resume-homework-faq-pending-gap",
    )

    assert len(backfilled_pending_events) == 1
    assert resumed_pending_events == []
    assert len(resumed_synced_events) == 1


def test_review_resume_sync_upgrades_legacy_pending_audit_in_place(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    approve_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert approve_response.status_code == 500
    pending_candidate = get_candidate(settings, candidate.candidate_id)
    assert pending_candidate.status is CandidateStatus.PROMOTED
    assert pending_candidate.wiki_sync_status is WikiSyncStatus.PENDING

    original_pending_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    assert len(original_pending_events) == 1

    with sqlite3.connect(settings.audit_db_path) as connection:
        connection.execute(
            "UPDATE audit_events SET details_json = NULL WHERE event_id = ?",
            (original_pending_events[0].event_id,),
        )
        connection.commit()

    resume_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-upgrade-pending-legacy",
            idempotency_key="idem-fixture-resume-homework-faq-upgrade-pending-legacy",
            domain="academic",
        ),
        json={"resume_notes": "Resume after transient write failure."},
    )

    assert resume_response.status_code == 200
    backfilled_pending_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
    )
    resumed_pending_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
        idempotency_key="idem-fixture-resume-homework-faq-upgrade-pending-legacy",
    )
    synced_candidate = get_candidate(settings, candidate.candidate_id)

    assert len(backfilled_pending_events) == 1
    assert resumed_pending_events == []
    assert backfilled_pending_events[0].details == {
        "candidate_id": synced_candidate.candidate_id,
        "promotion_attempt_id": synced_candidate.promotion_attempt_id,
        "approval_plan_fingerprint": synced_candidate.approval_plan_fingerprint,
    }


def test_review_resume_sync_replays_stored_response_after_finalize_marker_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    written_path = seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 500

    original_mark_applied = review_service.mark_mutation_request_applied
    finalize_attempts = {"count": 0}

    def flaky_mark_applied(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        if kwargs.get("action") == review_service.RESUME_SYNC_REQUEST_ACTION:
            finalize_attempts["count"] += 1
            if finalize_attempts["count"] == 1:
                raise OSError("forced resume finalize marker failure")
        return original_mark_applied(*args, **kwargs)

    monkeypatch.setattr(review_service, "mark_mutation_request_applied", flaky_mark_applied)

    failed_resume = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-finalize-fail",
            idempotency_key="idem-fixture-resume-homework-faq-finalize-fail",
            domain="academic",
        ),
        json={"resume_notes": "Resume after a transient finalization marker failure."},
    )

    assert failed_resume.status_code == 500

    recovered_candidate = get_candidate(settings, candidate.candidate_id)
    assert recovered_candidate.wiki_sync_status is WikiSyncStatus.SYNCED

    resume_request = get_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action=review_service.RESUME_SYNC_REQUEST_ACTION,
        idempotency_key="idem-fixture-resume-homework-faq-finalize-fail",
    )
    assert resume_request is not None
    assert resume_request.status == "pending"
    assert resume_request.response_payload is not None

    written_path.write_text(
        "not valid markdown frontmatter",
        encoding="utf-8",
    )

    replay_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-finalize-fail-replay",
            idempotency_key="idem-fixture-resume-homework-faq-finalize-fail",
            domain="academic",
        ),
        json={"resume_notes": "Resume after a transient finalization marker failure."},
    )

    assert replay_response.status_code == 200
    assert_server_owned_request_id(
        replay_response,
        client_request_id="req-fixture-resume-homework-faq-finalize-fail-replay",
    )
    replay_payload = replay_response.json()["data"]
    assert replay_payload["candidate"]["wiki_sync_status"] == "synced"
    assert replay_payload["patch"]["target_page_id"] == "page-faq-homework-submission"
    assert_client_request_id_not_persisted(
        settings,
        candidate=get_candidate(settings, candidate.candidate_id),
        client_request_id="req-fixture-resume-homework-faq-finalize-fail-replay",
        idempotency_key="idem-fixture-resume-homework-faq-finalize-fail",
        mutation_action="candidate_wiki_sync_resumed",
        wiki_contract_path="data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    finalized_request = get_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action=review_service.RESUME_SYNC_REQUEST_ACTION,
        idempotency_key="idem-fixture-resume-homework-faq-finalize-fail",
    )
    assert finalized_request is not None
    assert finalized_request.status == "applied"
    assert finalized_request.response_payload is not None
    assert review_service.ReviewActionResponse.model_validate(
        finalized_request.response_payload
    ) == review_service.ReviewActionResponse.model_validate(replay_payload)
    assert (
        finalized_request.response_payload["candidate"]["promotion_attempt_id"]
        == replay_payload["candidate"]["promotion_attempt_id"]
    )


def test_review_resume_sync_replays_from_stored_contract_after_candidate_metadata_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 500

    resume_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-metadata-drift",
            idempotency_key="idem-fixture-resume-homework-faq-metadata-drift",
            domain="academic",
        ),
        json={"resume_notes": "Resume after transient write failure."},
    )

    assert resume_response.status_code == 200
    replay_payload = resume_response.json()["data"]
    stored_candidate = get_candidate(settings, candidate.candidate_id)
    expected_resume_contract = {
        "promotion_attempt_id": stored_candidate.promotion_attempt_id,
        "approval_plan_fingerprint": stored_candidate.approval_plan_fingerprint,
    }

    candidate_path = build_candidate_path(settings, stored_candidate)
    drifted_candidate = stored_candidate.model_copy(
        update={
            "promotion_attempt_id": None,
            "approval_plan_fingerprint": None,
            "wiki_sync_target_path": None,
        }
    )
    candidate_path.write_text(
        json.dumps(drifted_candidate.model_dump(mode="json", exclude_none=True), indent=2) + "\n",
        encoding="utf-8",
    )

    replay_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-metadata-drift-replay",
            idempotency_key="idem-fixture-resume-homework-faq-metadata-drift",
            domain="academic",
        ),
        json={"resume_notes": "Resume after transient write failure."},
    )

    assert replay_response.status_code == 200
    assert replay_response.json()["data"] == replay_payload
    assert_server_owned_request_id(
        replay_response,
        client_request_id="req-fixture-resume-homework-faq-metadata-drift-replay",
    )

    finalized_request = get_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action=review_service.RESUME_SYNC_REQUEST_ACTION,
        idempotency_key="idem-fixture-resume-homework-faq-metadata-drift",
    )
    assert finalized_request is not None
    assert finalized_request.response_payload is not None
    assert (
        finalized_request.response_payload["candidate"]["promotion_attempt_id"]
        == expected_resume_contract["promotion_attempt_id"]
    )
    assert (
        finalized_request.response_payload["candidate"]["approval_plan_fingerprint"]
        == expected_resume_contract["approval_plan_fingerprint"]
    )
    assert finalized_request.response_payload["_resume_contract"] == expected_resume_contract


def test_review_resume_sync_replays_from_legacy_response_candidate_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    approve_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )
    assert approve_response.status_code == 500

    resume_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-legacy-contract",
            idempotency_key="idem-fixture-resume-homework-faq-legacy-contract",
            domain="academic",
        ),
        json={"resume_notes": "Resume after transient write failure."},
    )
    assert resume_response.status_code == 200
    expected_payload = resume_response.json()["data"]

    finalized_request = get_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action=review_service.RESUME_SYNC_REQUEST_ACTION,
        idempotency_key="idem-fixture-resume-homework-faq-legacy-contract",
    )
    assert finalized_request is not None
    assert finalized_request.response_payload is not None
    legacy_payload = dict(finalized_request.response_payload)
    legacy_payload.pop("_resume_contract", None)
    store_mutation_request_response_payload(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action=review_service.RESUME_SYNC_REQUEST_ACTION,
        idempotency_key="idem-fixture-resume-homework-faq-legacy-contract",
        updated_at=finalized_request.updated_at,
        response_payload=legacy_payload,
    )

    stored_candidate = get_candidate(settings, candidate.candidate_id)
    expected_resume_contract = {
        "promotion_attempt_id": stored_candidate.promotion_attempt_id,
        "approval_plan_fingerprint": stored_candidate.approval_plan_fingerprint,
    }
    candidate_path = build_candidate_path(settings, stored_candidate)
    drifted_candidate = stored_candidate.model_copy(
        update={
            "promotion_attempt_id": None,
            "approval_plan_fingerprint": None,
            "wiki_sync_target_path": None,
        }
    )
    candidate_path.write_text(
        json.dumps(drifted_candidate.model_dump(mode="json", exclude_none=True), indent=2) + "\n",
        encoding="utf-8",
    )

    replay_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-legacy-contract-replay",
            idempotency_key="idem-fixture-resume-homework-faq-legacy-contract",
            domain="academic",
        ),
        json={"resume_notes": "Resume after transient write failure."},
    )

    assert replay_response.status_code == 200
    assert replay_response.json()["data"] == expected_payload
    assert_server_owned_request_id(
        replay_response,
        client_request_id="req-fixture-resume-homework-faq-legacy-contract-replay",
    )

    replayed_request = get_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action=review_service.RESUME_SYNC_REQUEST_ACTION,
        idempotency_key="idem-fixture-resume-homework-faq-legacy-contract",
    )
    assert replayed_request is not None
    assert replayed_request.response_payload is not None
    assert (
        replayed_request.response_payload["candidate"]["promotion_attempt_id"]
        == expected_resume_contract["promotion_attempt_id"]
    )
    assert (
        replayed_request.response_payload["candidate"]["approval_plan_fingerprint"]
        == expected_resume_contract["approval_plan_fingerprint"]
    )
    assert replayed_request.response_payload["_resume_contract"] == expected_resume_contract


def test_review_resume_sync_reuses_same_audit_chain_after_mark_candidate_sync_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    approve_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert approve_response.status_code == 500

    original_mark_candidate_wiki_synced = review_service.mark_candidate_wiki_synced
    sync_attempts = {"count": 0}

    def flaky_mark_candidate_wiki_synced(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        sync_attempts["count"] += 1
        if sync_attempts["count"] == 1:
            raise OSError("forced candidate sync write failure")
        return original_mark_candidate_wiki_synced(*args, **kwargs)

    monkeypatch.setattr(
        review_service,
        "mark_candidate_wiki_synced",
        flaky_mark_candidate_wiki_synced,
    )

    failed_resume = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-sync-fail",
            idempotency_key="idem-fixture-resume-homework-faq-sync-fail",
            domain="academic",
        ),
        json={"resume_notes": "Resume after a transient candidate sync failure."},
    )

    assert failed_resume.status_code == 500
    pending_candidate = get_candidate(settings, candidate.candidate_id)
    assert pending_candidate.wiki_sync_status is WikiSyncStatus.PENDING

    replay_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-sync-fail-replay",
            idempotency_key="idem-fixture-resume-homework-faq-sync-fail",
            domain="academic",
        ),
        json={"resume_notes": "Resume after a transient candidate sync failure."},
    )

    assert replay_response.status_code == 200
    recovered_candidate = get_candidate(settings, candidate.candidate_id)
    assert recovered_candidate.wiki_sync_status is WikiSyncStatus.SYNCED

    resumed_synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        idempotency_key="idem-fixture-resume-homework-faq-sync-fail",
    )
    resumed_wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-resume-homework-faq-sync-fail",
    )

    assert len(resumed_synced_events) == 1
    assert len(resumed_wiki_audit) == 1


def test_review_resume_sync_appends_structured_wiki_patch_audit_across_fresh_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    write_failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not write_failed_once["value"]:
            write_failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    approve_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )
    assert approve_response.status_code == 500

    original_mark_candidate_wiki_synced = review_service.mark_candidate_wiki_synced
    sync_attempts = {"count": 0}

    def flaky_mark_candidate_wiki_synced(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        sync_attempts["count"] += 1
        if sync_attempts["count"] == 1:
            raise OSError("forced candidate sync write failure")
        return original_mark_candidate_wiki_synced(*args, **kwargs)

    monkeypatch.setattr(
        review_service,
        "mark_candidate_wiki_synced",
        flaky_mark_candidate_wiki_synced,
    )

    first_resume = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-first-key",
            idempotency_key="idem-fixture-resume-homework-faq-first-key",
            domain="academic",
        ),
        json={"resume_notes": "Resume after a transient candidate sync failure."},
    )
    assert first_resume.status_code == 500

    first_key_wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-resume-homework-faq-first-key",
    )
    assert len(first_key_wiki_audit) == 1
    with sqlite3.connect(settings.audit_db_path) as connection:
        connection.execute(
            "UPDATE audit_events SET details_json = NULL WHERE event_id = ?",
            (first_key_wiki_audit[0].event_id,),
        )
        connection.commit()

    second_resume = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-second-key",
            idempotency_key="idem-fixture-resume-homework-faq-second-key",
            domain="academic",
        ),
        json={"resume_notes": "Resume after a transient candidate sync failure."},
    )
    assert second_resume.status_code == 200

    second_key_wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-resume-homework-faq-second-key",
    )
    synced_events_second_key = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        idempotency_key="idem-fixture-resume-homework-faq-second-key",
    )
    all_wiki_patch_events = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
    )
    synced_candidate = get_candidate(settings, candidate.candidate_id)

    assert len(second_key_wiki_audit) == 1
    assert len(synced_events_second_key) == 1
    assert len(all_wiki_patch_events) == 2
    assert second_key_wiki_audit[0].details == {
        "candidate_id": synced_candidate.candidate_id,
        "promotion_attempt_id": synced_candidate.promotion_attempt_id,
        "approval_plan_fingerprint": synced_candidate.approval_plan_fingerprint,
    }
    assert all_wiki_patch_events[1].details is None


def test_review_resume_sync_reuses_single_legacy_page_audit_for_same_key_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    approve_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )
    assert approve_response.status_code == 500

    resume_headers = build_headers(
        role="instructor",
        actor_id="ins-calculus-team",
        request_id="req-fixture-resume-homework-faq-legacy-page-replay",
        idempotency_key="idem-fixture-resume-homework-faq-legacy-page-replay",
        domain="academic",
    )
    resume_payload = {"resume_notes": "Resume after transient write failure."}

    first_resume = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=resume_headers,
        json=resume_payload,
    )
    assert first_resume.status_code == 200
    first_payload = first_resume.json()["data"]

    first_key_wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-resume-homework-faq-legacy-page-replay",
    )
    assert len(first_key_wiki_audit) == 1

    with sqlite3.connect(settings.audit_db_path) as connection:
        connection.execute(
            "UPDATE audit_events SET details_json = NULL WHERE event_id = ?",
            (first_key_wiki_audit[0].event_id,),
        )
        connection.commit()

    replay_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-legacy-page-replay-02",
            idempotency_key="idem-fixture-resume-homework-faq-legacy-page-replay",
            domain="academic",
        ),
        json=resume_payload,
    )
    assert replay_response.status_code == 200
    assert replay_response.json()["data"] == first_payload

    same_key_wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-resume-homework-faq-legacy-page-replay",
    )
    all_wiki_patch_events = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
    )

    assert len(same_key_wiki_audit) == 1
    assert len(all_wiki_patch_events) == 1
    synced_candidate = get_candidate(settings, candidate.candidate_id)
    assert all_wiki_patch_events[0].details == {
        "candidate_id": candidate.candidate_id,
        "promotion_attempt_id": synced_candidate.promotion_attempt_id,
        "approval_plan_fingerprint": synced_candidate.approval_plan_fingerprint,
    }


def test_review_resume_sync_does_not_upgrade_legacy_synced_audit_when_history_is_ambiguous(
    tmp_path: Path,
) -> None:
    import knowloop_api.services.review as review_service

    _, settings = build_client(tmp_path)
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    candidate = candidate.model_copy(
        update={
            "status": CandidateStatus.PROMOTED,
            "promotion_attempt_id": "promote-current",
            "approval_plan_fingerprint": "plan-current",
            "wiki_sync_status": WikiSyncStatus.PENDING,
            "related_page_id": "page-faq-homework-submission",
            "wiki_sync_target_path": (
                "wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md"
            ),
        }
    )
    build_candidate_path(settings, candidate).write_text(
        json.dumps(candidate.model_dump(mode="json", exclude_none=True), indent=2) + "\n",
        encoding="utf-8",
    )

    create_audit_event(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
        actor_role="instructor",
        actor_id="ins-calculus-team",
        created_at=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
    )
    create_audit_event(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
        actor_role="instructor",
        actor_id="ins-calculus-team",
        created_at=datetime(2026, 3, 2, 10, 0, tzinfo=UTC),
    )
    create_audit_event(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        actor_role="instructor",
        actor_id="ins-calculus-team",
        created_at=datetime(2026, 3, 2, 10, 1, tzinfo=UTC),
    )

    assert (
        review_service._ensure_candidate_owned_wiki_sync_audit_event(
            settings,
            entity_id=candidate.candidate_id,
            action="candidate_wiki_synced",
            details={
                "candidate_id": candidate.candidate_id,
                "promotion_attempt_id": candidate.promotion_attempt_id,
                "approval_plan_fingerprint": candidate.approval_plan_fingerprint,
            },
        )
        is False
    )

    synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
    )
    assert len(synced_events) == 1
    assert synced_events[0].details is None


def test_review_resume_sync_does_not_upgrade_legacy_page_audit_without_matching_candidate_chain(
    tmp_path: Path,
) -> None:
    import knowloop_api.services.review as review_service

    _, settings = build_client(tmp_path)
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")

    create_audit_event(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        actor_role="instructor",
        actor_id="ins-calculus-team",
        idempotency_key="idem-legacy-page-only",
        created_at=datetime(2026, 3, 2, 10, 2, tzinfo=UTC),
    )

    assert (
        review_service._ensure_page_owned_wiki_patch_audit_event(
            settings,
            page_id="page-faq-homework-submission",
            details={
                "candidate_id": candidate.candidate_id,
                "promotion_attempt_id": "promote-current",
                "approval_plan_fingerprint": "plan-current",
            },
            idempotency_key="idem-legacy-page-only",
        )
        is False
    )

    page_events = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
    )
    assert len(page_events) == 1
    assert page_events[0].details is None


def test_review_resume_sync_replays_stored_success_after_status_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    approve_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )
    assert approve_response.status_code == 500

    resume_headers = build_headers(
        role="instructor",
        actor_id="ins-calculus-team",
        request_id="req-fixture-resume-homework-faq-status-drift",
        idempotency_key="idem-fixture-resume-homework-faq-status-drift",
        domain="academic",
    )
    resume_payload = {"resume_notes": "Resume after transient write failure."}

    first_resume = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=resume_headers,
        json=resume_payload,
    )
    assert first_resume.status_code == 200
    expected_payload = first_resume.json()["data"]
    initial_wiki_patch_events = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-resume-homework-faq-status-drift",
    )
    initial_synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        idempotency_key="idem-fixture-resume-homework-faq-status-drift",
    )
    initial_pending_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
    )
    assert len(initial_wiki_patch_events) == 1
    assert len(initial_synced_events) == 1
    assert len(initial_pending_events) == 1
    with sqlite3.connect(settings.audit_db_path) as connection:
        connection.execute(
            "UPDATE audit_events SET details_json = NULL WHERE event_id = ?",
            (initial_pending_events[0].event_id,),
        )
        connection.commit()

    stored_candidate = get_candidate(settings, candidate.candidate_id)
    candidate_path = build_candidate_path(settings, stored_candidate)
    drifted_candidate = stored_candidate.model_copy(
        update={
            "status": CandidateStatus.PROMOTED,
            "wiki_sync_status": WikiSyncStatus.PENDING,
            "wiki_synced_at": None,
        }
    )
    candidate_path.write_text(
        json.dumps(drifted_candidate.model_dump(mode="json", exclude_none=True), indent=2) + "\n",
        encoding="utf-8",
    )

    def fail_if_wiki_rewritten(path: Path, contents: str) -> None:
        raise AssertionError("applied resume replay must not rewrite wiki content")

    monkeypatch.setattr(review_service, "_write_wiki_page", fail_if_wiki_rewritten)

    replay_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-status-drift-replay",
            idempotency_key="idem-fixture-resume-homework-faq-status-drift",
            domain="academic",
        ),
        json=resume_payload,
    )
    assert replay_response.status_code == 200
    assert replay_response.json()["data"] == expected_payload
    assert_server_owned_request_id(
        replay_response,
        client_request_id="req-fixture-resume-homework-faq-status-drift-replay",
    )
    repaired_candidate = get_candidate(settings, candidate.candidate_id)
    assert repaired_candidate.wiki_sync_status is WikiSyncStatus.SYNCED
    assert repaired_candidate.wiki_synced_at is not None
    replay_wiki_patch_events = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-resume-homework-faq-status-drift",
    )
    replay_synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        idempotency_key="idem-fixture-resume-homework-faq-status-drift",
    )
    replay_pending_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
    )
    assert len(replay_wiki_patch_events) == len(initial_wiki_patch_events)
    assert len(replay_synced_events) == len(initial_synced_events)
    assert len(replay_pending_events) == len(initial_pending_events)
    assert replay_pending_events[0].details == {
        "candidate_id": candidate.candidate_id,
        "promotion_attempt_id": repaired_candidate.promotion_attempt_id,
        "approval_plan_fingerprint": repaired_candidate.approval_plan_fingerprint,
    }


def test_review_approve_replay_requires_finalize_role_even_with_existing_request(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )
    assert first_response.status_code == 200

    replay_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=build_headers(
            role="system",
            actor_id="system-replay",
            request_id="req-review-approve-replay-system",
            idempotency_key=review_fixture["request_headers"]["Idempotency-Key"],
            domain="review",
        ),
        json=review_fixture["request_body"],
    )
    assert replay_response.status_code == 403
    assert_api_error_envelope(
        replay_response,
        expected_code="forbidden_role",
        client_request_id="req-review-approve-replay-system",
    )


def test_review_merge_replay_requires_finalize_role_even_with_existing_request(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    source_candidate = seed_candidate(settings, "open-misconception-chain-rule.json")
    target_candidate = seed_candidate(settings, "open-misconception-chain-rule-duplicate.json")
    merge_headers = build_headers(
        role="instructor",
        actor_id="ins-calculus-team",
        request_id="req-review-merge-replay-1",
        idempotency_key="idem-review-merge-replay-1",
        domain="academic",
    )
    merge_payload = {
        "target_candidate_id": target_candidate.candidate_id,
        "merge_notes": "Merge duplicate unresolved integral question.",
    }

    first_response = client.post(
        f"/api/v1/review/candidates/{source_candidate.candidate_id}/merge",
        headers=merge_headers,
        json=merge_payload,
    )
    assert first_response.status_code == 200

    replay_response = client.post(
        f"/api/v1/review/candidates/{source_candidate.candidate_id}/merge",
        headers=build_headers(
            role="system",
            actor_id="system-replay",
            request_id="req-review-merge-replay-system",
            idempotency_key="idem-review-merge-replay-1",
            domain="review",
        ),
        json=merge_payload,
    )
    assert replay_response.status_code == 403
    assert_api_error_envelope(
        replay_response,
        expected_code="forbidden_role",
        client_request_id="req-review-merge-replay-system",
    )


def test_review_drop_replay_requires_finalize_role_even_with_existing_request(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    candidate = seed_candidate(settings, "open-unresolved-integral.json")
    drop_headers = build_headers(
        role="instructor",
        actor_id="ins-calculus-team",
        request_id="req-review-drop-replay-1",
        idempotency_key="idem-review-drop-replay-1",
        domain="academic",
    )
    drop_payload = {
        "reason": "superseded_by_existing_candidate",
        "drop_notes": "Duplicate unresolved question already covered by another candidate.",
    }

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/drop",
        headers=drop_headers,
        json=drop_payload,
    )
    assert first_response.status_code == 200

    replay_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/drop",
        headers=build_headers(
            role="system",
            actor_id="system-replay",
            request_id="req-review-drop-replay-system",
            idempotency_key="idem-review-drop-replay-1",
            domain="review",
        ),
        json=drop_payload,
    )
    assert replay_response.status_code == 403
    assert_api_error_envelope(
        replay_response,
        expected_code="forbidden_role",
        client_request_id="req-review-drop-replay-system",
    )


def test_review_resume_sync_replay_requires_finalize_role_even_with_existing_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    approve_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )
    assert approve_response.status_code == 500

    resume_payload = {"resume_notes": "Resume after transient write failure."}
    resume_headers = build_headers(
        role="instructor",
        actor_id="ins-calculus-team",
        request_id="req-review-resume-replay-1",
        idempotency_key="idem-review-resume-replay-1",
        domain="academic",
    )
    first_resume = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=resume_headers,
        json=resume_payload,
    )
    assert first_resume.status_code == 200

    replay_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="system",
            actor_id="system-replay",
            request_id="req-review-resume-replay-system",
            idempotency_key="idem-review-resume-replay-1",
            domain="review",
        ),
        json=resume_payload,
    )
    assert replay_response.status_code == 403
    assert_api_error_envelope(
        replay_response,
        expected_code="forbidden_role",
        client_request_id="req-review-resume-replay-system",
    )


def test_review_resume_sync_backfills_missing_synced_audit_after_partial_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    approve_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert approve_response.status_code == 500

    original_record_candidate_wiki_synced = review_service._record_candidate_wiki_synced
    synced_audit_attempts = {"count": 0}

    def flaky_record_candidate_wiki_synced(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        synced_audit_attempts["count"] += 1
        if synced_audit_attempts["count"] == 1:
            raise OSError("forced candidate synced audit failure")
        return original_record_candidate_wiki_synced(*args, **kwargs)

    monkeypatch.setattr(
        review_service,
        "_record_candidate_wiki_synced",
        flaky_record_candidate_wiki_synced,
    )

    failed_resume = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-synced-audit-fail",
            idempotency_key="idem-fixture-resume-homework-faq-synced-audit-fail",
            domain="academic",
        ),
        json={"resume_notes": "Resume after a transient synced-audit failure."},
    )

    assert failed_resume.status_code == 500
    synced_candidate = get_candidate(settings, candidate.candidate_id)
    assert synced_candidate.wiki_sync_status is WikiSyncStatus.SYNCED

    replay_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-synced-audit-fail-replay",
            idempotency_key="idem-fixture-resume-homework-faq-synced-audit-fail",
            domain="academic",
        ),
        json={"resume_notes": "Resume after a transient synced-audit failure."},
    )

    assert replay_response.status_code == 200

    resumed_synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        idempotency_key="idem-fixture-resume-homework-faq-synced-audit-fail",
    )
    resumed_wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-resume-homework-faq-synced-audit-fail",
    )

    assert len(resumed_synced_events) == 1
    assert len(resumed_wiki_audit) == 1


def test_review_resume_sync_rejects_reused_idempotency_key_with_different_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 500

    resume_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-conflict-base",
            idempotency_key="idem-fixture-resume-homework-faq-conflict",
            domain="academic",
        ),
        json={"resume_notes": "Resume the stored approval plan."},
    )

    assert resume_response.status_code == 200

    conflict_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-conflict-second",
            idempotency_key="idem-fixture-resume-homework-faq-conflict",
            domain="academic",
        ),
        json={"resume_notes": "Resume the stored approval plan with a different note."},
    )

    assert conflict_response.status_code == 409
    assert_api_error_envelope(
        conflict_response,
        expected_code="duplicate_action",
        client_request_id="req-fixture-resume-homework-faq-conflict-second",
    )
    assert_client_request_id_not_persisted(
        settings,
        candidate=get_candidate(settings, candidate.candidate_id),
        client_request_id="req-fixture-resume-homework-faq-conflict-second",
        idempotency_key="idem-fixture-resume-homework-faq-conflict",
        mutation_action="candidate_wiki_sync_resumed",
        wiki_contract_path="data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )


def test_review_resume_sync_returns_duplicate_action_when_stored_plan_drifts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    written_path = seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 500
    written_path.write_text(
        written_path.read_text(encoding="utf-8").replace(
            "Submit Homework 01 through the LMS assignment page.",
            "Submit Homework 01 through the course forum instead.",
        ),
        encoding="utf-8",
    )
    artifact_snapshot = capture_review_artifact_snapshot(
        settings,
        candidates=(get_candidate(settings, candidate.candidate_id),),
        wiki_contract_paths=(
            "data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
        ),
    )

    resume_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-drift",
            idempotency_key="idem-fixture-resume-homework-faq-drift",
            domain="academic",
        ),
        json={"resume_notes": "Resume the frozen approval plan after the write failure."},
    )

    stored_candidate = get_candidate(settings, candidate.candidate_id)
    synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        idempotency_key="idem-fixture-resume-homework-faq-drift",
    )
    wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-resume-homework-faq-drift",
    )

    assert resume_response.status_code == 409
    assert_api_error_envelope(
        resume_response,
        expected_code="duplicate_action",
        client_request_id="req-fixture-resume-homework-faq-drift",
    )
    assert stored_candidate.status is CandidateStatus.PROMOTED
    assert stored_candidate.wiki_sync_status is WikiSyncStatus.PENDING
    assert synced_events == []
    assert wiki_audit == []
    assert_no_review_mutation_artifacts(
        settings,
        candidate_id=candidate.candidate_id,
        mutation_action="candidate_wiki_sync_resumed",
        idempotency_key="idem-fixture-resume-homework-faq-drift",
        artifact_snapshot=artifact_snapshot,
    )


def test_review_resume_sync_returns_duplicate_action_when_target_page_drifts_out_of_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    written_path = seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 500
    written_path.write_text(
        written_path.read_text(encoding="utf-8").replace(
            "class_scope: class-calculus-1-2026-spring-a",
            "class_scope: class-calculus-1-2026-spring-b",
        ),
        encoding="utf-8",
    )
    artifact_snapshot = capture_review_artifact_snapshot(
        settings,
        candidates=(get_candidate(settings, candidate.candidate_id),),
        wiki_contract_paths=(
            "data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
            "data/wiki/faq/class-calculus-1-2026-spring-b/homework-submission.md",
        ),
    )

    resume_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-scope-drift",
            idempotency_key="idem-fixture-resume-homework-faq-scope-drift",
            domain="academic",
        ),
        json={"resume_notes": "Resume the frozen approval plan after a scope drift."},
    )

    assert resume_response.status_code == 409
    assert_api_error_envelope(
        resume_response,
        expected_code="duplicate_action",
        client_request_id="req-fixture-resume-homework-faq-scope-drift",
    )
    assert_no_review_mutation_artifacts(
        settings,
        candidate_id=candidate.candidate_id,
        mutation_action="candidate_wiki_sync_resumed",
        idempotency_key="idem-fixture-resume-homework-faq-scope-drift",
        artifact_snapshot=artifact_snapshot,
    )


def test_review_resume_sync_returns_duplicate_action_when_target_page_drifts_to_other_course(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    written_path = seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 500
    written_path.write_text(
        written_path.read_text(encoding="utf-8").replace(
            "course_id: course-calculus-1",
            "course_id: course-linear-algebra-1",
        ),
        encoding="utf-8",
    )
    artifact_snapshot = capture_review_artifact_snapshot(
        settings,
        candidates=(get_candidate(settings, candidate.candidate_id),),
        wiki_contract_paths=(
            "data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
        ),
    )

    resume_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-fixture-resume-homework-faq-course-drift",
            idempotency_key="idem-fixture-resume-homework-faq-course-drift",
            domain="academic",
        ),
        json={
            "resume_notes": "Resume should fail when the approved page drifts to another course."
        },
    )

    assert resume_response.status_code == 409
    assert_api_error_envelope(
        resume_response,
        expected_code="duplicate_action",
        client_request_id="req-fixture-resume-homework-faq-course-drift",
    )
    assert_no_review_mutation_artifacts(
        settings,
        candidate_id=candidate.candidate_id,
        mutation_action="candidate_wiki_sync_resumed",
        idempotency_key="idem-fixture-resume-homework-faq-course-drift",
        artifact_snapshot=artifact_snapshot,
    )


def test_review_approve_recovers_after_wiki_patch_audit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    written_path = seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )
    expected_after_contents = (
        FIXTURE_ROOT / "wiki" / "faq-homework-submission.after.md"
    ).read_text(encoding="utf-8")

    original_record_wiki_patch_applied = review_service._record_wiki_patch_applied
    failed_once = {"value": False}

    def flaky_record_wiki_patch_applied(*args, **kwargs):
        if not failed_once["value"]:
            failed_once["value"] = True
            raise RuntimeError("forced wiki audit failure")
        return original_record_wiki_patch_applied(*args, **kwargs)

    monkeypatch.setattr(
        review_service,
        "_record_wiki_patch_applied",
        flaky_record_wiki_patch_applied,
    )

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 500
    assert_api_error_envelope(
        first_response,
        expected_code="internal_error",
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )
    assert written_path.exists()
    first_failed_candidate = get_candidate(settings, candidate.candidate_id)
    assert first_failed_candidate.status is CandidateStatus.PROMOTED
    assert first_failed_candidate.wiki_sync_status is WikiSyncStatus.PENDING
    assert first_failed_candidate.wiki_synced_at is None
    assert_client_request_id_not_persisted(
        settings,
        candidate=first_failed_candidate,
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
        idempotency_key="idem-fixture-approve-homework-faq",
        mutation_action="candidate_promoted",
        wiki_contract_path="data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    promoted_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    pending_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        idempotency_key="idem-fixture-approve-homework-faq",
    )

    first_metadata, first_body = parse_markdown_document(written_path.read_text(encoding="utf-8"))
    expected_metadata, expected_body = parse_markdown_document(expected_after_contents)
    assert first_body == expected_body
    assert first_metadata["candidate_refs"] == expected_metadata["candidate_refs"]
    assert first_metadata["source_refs"] == expected_metadata["source_refs"]
    assert len(promoted_events) == 1
    assert len(pending_events) == 1
    assert len(wiki_audit) == 0
    assert len(synced_events) == 0

    second_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert second_response.status_code == 200
    assert_server_owned_request_id(
        second_response,
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )
    recovered_candidate = get_candidate(settings, candidate.candidate_id)
    assert recovered_candidate.status is CandidateStatus.PROMOTED
    assert recovered_candidate.wiki_sync_status is WikiSyncStatus.SYNCED
    assert_client_request_id_not_persisted(
        settings,
        candidate=recovered_candidate,
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
        idempotency_key="idem-fixture-approve-homework-faq",
        mutation_action="candidate_promoted",
        wiki_contract_path="data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    promoted_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    pending_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        idempotency_key="idem-fixture-approve-homework-faq",
    )

    final_metadata, final_body = parse_markdown_document(written_path.read_text(encoding="utf-8"))
    assert final_body == expected_body
    assert final_metadata["candidate_refs"] == expected_metadata["candidate_refs"]
    assert final_metadata["source_refs"] == expected_metadata["source_refs"]
    assert len(promoted_events) == 1
    assert len(pending_events) == 1
    assert len(wiki_audit) == 1
    assert len(synced_events) == 1


def test_review_approve_rejects_replay_when_patch_plan_drifts_after_partial_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    written_path = seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 500
    written_path.write_text(
        written_path.read_text(encoding="utf-8").replace(
            "Submit Homework 01 through the LMS assignment page.",
            "Submit Homework 01 through the course forum instead.",
        ),
        encoding="utf-8",
    )

    second_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers={
            **review_fixture["request_headers"],
            "X-Request-Id": "req-fixture-approve-homework-faq-drifted-retry",
        },
        json=review_fixture["request_body"],
    )

    stored_candidate = get_candidate(settings, candidate.candidate_id)
    pending_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_sync_pending",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    wiki_audit = list_audit_events(
        settings,
        entity_type="wiki_page",
        entity_id="page-faq-homework-submission",
        action="wiki_patch_applied",
        idempotency_key="idem-fixture-approve-homework-faq",
    )
    synced_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_wiki_synced",
        idempotency_key="idem-fixture-approve-homework-faq",
    )

    assert second_response.status_code == 409
    assert_api_error_envelope(
        second_response,
        expected_code="duplicate_action",
        client_request_id="req-fixture-approve-homework-faq-drifted-retry",
    )
    assert_client_request_id_not_persisted(
        settings,
        candidate=stored_candidate,
        client_request_id="req-fixture-approve-homework-faq-drifted-retry",
        idempotency_key="idem-fixture-approve-homework-faq",
        mutation_action="candidate_promoted",
        wiki_contract_path="data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )
    assert stored_candidate.status is CandidateStatus.PROMOTED
    assert stored_candidate.wiki_sync_status is WikiSyncStatus.PENDING
    assert stored_candidate.wiki_synced_at is None
    assert len(pending_events) == 1
    assert wiki_audit == []
    assert synced_events == []


def test_review_approve_replay_returns_duplicate_action_when_target_page_drifts_out_of_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    written_path = seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 500
    assert_api_error_envelope(
        first_response,
        expected_code="internal_error",
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )
    assert_client_request_id_not_persisted(
        settings,
        candidate=get_candidate(settings, candidate.candidate_id),
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
        idempotency_key="idem-fixture-approve-homework-faq",
        mutation_action="candidate_promoted",
        wiki_contract_path="data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )
    written_path.write_text(
        written_path.read_text(encoding="utf-8").replace(
            "class_scope: class-calculus-1-2026-spring-a",
            "class_scope: class-calculus-1-2026-spring-b",
        ),
        encoding="utf-8",
    )

    second_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers={
            **review_fixture["request_headers"],
            "X-Request-Id": "req-fixture-approve-homework-faq-scope-drift-retry",
        },
        json=review_fixture["request_body"],
    )

    assert second_response.status_code == 409
    assert_api_error_envelope(
        second_response,
        expected_code="duplicate_action",
        client_request_id="req-fixture-approve-homework-faq-scope-drift-retry",
    )
    assert_client_request_id_not_persisted(
        settings,
        candidate=get_candidate(settings, candidate.candidate_id),
        client_request_id="req-fixture-approve-homework-faq-scope-drift-retry",
        idempotency_key="idem-fixture-approve-homework-faq",
        mutation_action="candidate_promoted",
        wiki_contract_path="data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )


def test_review_merge_endpoint_merges_duplicate_candidate(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("merge-chain-rule-duplicate.json")
    canonical_candidate = seed_candidate(settings, "open-misconception-chain-rule.json")
    duplicate_candidate = seed_candidate(settings, "open-misconception-chain-rule-duplicate.json")

    response = client.post(
        f"/api/v1/review/candidates/{duplicate_candidate.candidate_id}/merge",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert response.status_code == 200
    assert_server_owned_request_id(
        response,
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )
    payload = response.json()["data"]
    assert payload["candidate"]["status"] == "merged"
    assert payload["candidate"]["merged_into"] == canonical_candidate.candidate_id
    assert payload["target_candidate"]["candidate_id"] == canonical_candidate.candidate_id
    assert "duplicate" in payload["target_candidate"]["tags"]
    assert_client_request_id_not_persisted(
        settings,
        candidate=get_candidate(settings, duplicate_candidate.candidate_id),
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
        idempotency_key="idem-fixture-merge-chain-rule-dup",
        mutation_action="candidate_merged",
        additional_candidates=(get_candidate(settings, canonical_candidate.candidate_id),),
    )


def test_review_merge_returns_400_for_non_replay_state_errors(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("merge-chain-rule-duplicate.json")
    candidate = seed_candidate(settings, "open-misconception-chain-rule-duplicate.json")

    response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/merge",
        headers=review_fixture["request_headers"],
        json={
            "target_candidate_id": candidate.candidate_id,
            "merge_notes": "Reject merging a candidate into itself.",
        },
    )

    assert response.status_code == 400
    assert_api_error_envelope(
        response,
        expected_code="invalid_request",
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )


def test_review_merge_endpoint_is_idempotent_with_same_key(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("merge-chain-rule-duplicate.json")
    canonical_candidate = seed_candidate(settings, "open-misconception-chain-rule.json")
    duplicate_candidate = seed_candidate(settings, "open-misconception-chain-rule-duplicate.json")

    first_response = client.post(
        f"/api/v1/review/candidates/{duplicate_candidate.candidate_id}/merge",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )
    second_response = client.post(
        f"/api/v1/review/candidates/{duplicate_candidate.candidate_id}/merge",
        headers={
            **review_fixture["request_headers"],
            "X-Request-Id": "req-fixture-merge-chain-rule-dup-replay",
        },
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_request_id = assert_server_owned_request_id(
        first_response,
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )
    second_request_id = assert_server_owned_request_id(
        second_response,
        client_request_id="req-fixture-merge-chain-rule-dup-replay",
    )
    assert first_request_id != second_request_id
    assert (
        second_response.json()["data"]["candidate"]["merged_into"]
        == canonical_candidate.candidate_id
    )

    merge_audit = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=duplicate_candidate.candidate_id,
        action="candidate_merged",
        idempotency_key="idem-fixture-merge-chain-rule-dup",
    )
    assert len(merge_audit) == 1
    assert_client_request_id_not_persisted(
        settings,
        candidate=get_candidate(settings, duplicate_candidate.candidate_id),
        client_request_id="req-fixture-merge-chain-rule-dup-replay",
        idempotency_key="idem-fixture-merge-chain-rule-dup",
        mutation_action="candidate_merged",
        additional_candidates=(get_candidate(settings, canonical_candidate.candidate_id),),
    )


def test_review_merge_rejects_reused_idempotency_key_with_different_payload(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("merge-chain-rule-duplicate.json")
    canonical_candidate = seed_candidate(settings, "open-misconception-chain-rule.json")
    duplicate_candidate = seed_candidate(settings, "open-misconception-chain-rule-duplicate.json")

    first_response = client.post(
        f"/api/v1/review/candidates/{duplicate_candidate.candidate_id}/merge",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )
    second_response = client.post(
        f"/api/v1/review/candidates/{duplicate_candidate.candidate_id}/merge",
        headers={
            **review_fixture["request_headers"],
            "X-Request-Id": "req-fixture-merge-chain-rule-dup-conflict",
        },
        json={
            **review_fixture["request_body"],
            "merge_notes": "Conflicting merge notes for the same idempotency key.",
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    first_request_id = assert_server_owned_request_id(
        first_response,
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )
    second_request_id = assert_api_error_envelope(
        second_response,
        expected_code="duplicate_action",
        client_request_id="req-fixture-merge-chain-rule-dup-conflict",
    )
    assert first_request_id != second_request_id

    merge_audit = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=duplicate_candidate.candidate_id,
        action="candidate_merged",
        idempotency_key="idem-fixture-merge-chain-rule-dup",
    )
    assert len(merge_audit) == 1
    assert_client_request_id_not_persisted(
        settings,
        candidate=get_candidate(settings, duplicate_candidate.candidate_id),
        client_request_id="req-fixture-merge-chain-rule-dup-conflict",
        idempotency_key="idem-fixture-merge-chain-rule-dup",
        mutation_action="candidate_merged",
        additional_candidates=(get_candidate(settings, canonical_candidate.candidate_id),),
    )


def test_review_drop_endpoint_drops_candidate(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("drop-low-value-candidate.json")
    candidate = seed_candidate(settings, "open-unresolved-integral.json")

    response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/drop",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["candidate"]["status"] == "dropped"
    dropped_candidate = get_candidate(settings, candidate.candidate_id)
    assert dropped_candidate.status is CandidateStatus.DROPPED
    assert_client_request_id_not_persisted(
        settings,
        candidate=dropped_candidate,
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
        idempotency_key="idem-fixture-drop-low-value",
        mutation_action="candidate_dropped",
    )


def test_review_drop_endpoint_is_idempotent_with_same_key(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("drop-low-value-candidate.json")
    candidate = seed_candidate(settings, "open-unresolved-integral.json")

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/drop",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )
    second_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/drop",
        headers={
            **review_fixture["request_headers"],
            "X-Request-Id": "req-fixture-drop-low-value-replay",
        },
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_request_id = assert_server_owned_request_id(
        first_response,
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )
    second_request_id = assert_server_owned_request_id(
        second_response,
        client_request_id="req-fixture-drop-low-value-replay",
    )
    assert first_request_id != second_request_id
    assert second_response.json()["data"]["candidate"]["status"] == "dropped"

    drop_audit = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_dropped",
        idempotency_key="idem-fixture-drop-low-value",
    )
    assert len(drop_audit) == 1
    assert "Drop reason: insufficient_shared_value" in drop_audit[0].notes
    assert drop_audit[0].details == {"reason": "insufficient_shared_value"}
    assert_client_request_id_not_persisted(
        settings,
        candidate=get_candidate(settings, candidate.candidate_id),
        client_request_id="req-fixture-drop-low-value-replay",
        idempotency_key="idem-fixture-drop-low-value",
        mutation_action="candidate_dropped",
    )


def test_review_drop_rejects_reused_idempotency_key_with_different_payload(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("drop-low-value-candidate.json")
    candidate = seed_candidate(settings, "open-unresolved-integral.json")

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/drop",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )
    second_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/drop",
        headers={
            **review_fixture["request_headers"],
            "X-Request-Id": "req-fixture-drop-low-value-conflict",
        },
        json={
            **review_fixture["request_body"],
            "reason": "superseded_by_existing_candidate",
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    first_request_id = assert_server_owned_request_id(
        first_response,
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )
    second_request_id = assert_api_error_envelope(
        second_response,
        expected_code="duplicate_action",
        client_request_id="req-fixture-drop-low-value-conflict",
    )
    assert first_request_id != second_request_id

    drop_audit = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_dropped",
        idempotency_key="idem-fixture-drop-low-value",
    )
    assert len(drop_audit) == 1
    assert "Drop reason: insufficient_shared_value" in drop_audit[0].notes
    assert drop_audit[0].details == {"reason": "insufficient_shared_value"}
    assert_client_request_id_not_persisted(
        settings,
        candidate=get_candidate(settings, candidate.candidate_id),
        client_request_id="req-fixture-drop-low-value-conflict",
        idempotency_key="idem-fixture-drop-low-value",
        mutation_action="candidate_dropped",
    )


def test_review_drop_rejects_reused_idempotency_key_with_different_notes(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("drop-low-value-candidate.json")
    candidate = seed_candidate(settings, "open-unresolved-integral.json")

    first_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/drop",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )
    second_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/drop",
        headers={
            **review_fixture["request_headers"],
            "X-Request-Id": "req-fixture-drop-low-value-notes-conflict",
        },
        json={
            **review_fixture["request_body"],
            "drop_notes": "Same reason, different review notes.",
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    first_request_id = assert_server_owned_request_id(
        first_response,
        client_request_id=review_fixture["request_headers"]["X-Request-Id"],
    )
    second_request_id = assert_api_error_envelope(
        second_response,
        expected_code="duplicate_action",
        client_request_id="req-fixture-drop-low-value-notes-conflict",
    )
    assert first_request_id != second_request_id

    drop_audit = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_dropped",
        idempotency_key="idem-fixture-drop-low-value",
    )
    assert len(drop_audit) == 1
    assert "Drop reason: insufficient_shared_value" in drop_audit[0].notes
    assert drop_audit[0].details == {"reason": "insufficient_shared_value"}
    assert_client_request_id_not_persisted(
        settings,
        candidate=get_candidate(settings, candidate.candidate_id),
        client_request_id="req-fixture-drop-low-value-notes-conflict",
        idempotency_key="idem-fixture-drop-low-value",
        mutation_action="candidate_dropped",
    )
    assert drop_audit[0].details == {"reason": "insufficient_shared_value"}


def test_operator_can_list_operations_candidates_but_cannot_approve_them(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    candidate = seed_candidate(settings, "open-operations-refund.json")
    seed_source_fixture(settings, "operations-refund-policy.md")
    seed_wiki_fixture(
        settings,
        source_filename="operations-refund-policy.seed.md",
        target_relative_path="wiki/operations/class-calculus-1-2026-spring-a/refund-policy.md",
    )
    artifact_snapshot = capture_review_artifact_snapshot(
        settings,
        candidates=(candidate,),
        wiki_contract_paths=(
            "data/wiki/operations/class-calculus-1-2026-spring-a/refund-policy.md",
        ),
    )

    list_response = client.get(
        "/api/v1/review/candidates",
        headers=build_headers(
            role="operator",
            actor_id="ops-academic-office",
            request_id="req-operator-review-list",
        ),
    )
    approve_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=build_headers(
            role="operator",
            actor_id="ops-academic-office",
            request_id="req-operator-review-approve",
            idempotency_key="idem-operator-review-approve",
        ),
        json={
            "target_page_id": "page-operations-refund-policy",
            "target_path": "data/wiki/operations/class-calculus-1-2026-spring-a/refund-policy.md",
            "approval_notes": "Operator should not be able to finalize this promotion.",
        },
    )
    detail_response = client.get(
        f"/api/v1/review/candidates/{candidate.candidate_id}",
        headers=build_headers(
            role="operator",
            actor_id="ops-academic-office",
            request_id="req-operator-review-detail",
        ),
    )
    preview_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/patch-preview",
        headers=build_headers(
            role="operator",
            actor_id="ops-academic-office",
            request_id="req-operator-review-preview",
        ),
        json={
            "target_page_id": "page-operations-refund-policy",
            "target_path": "data/wiki/operations/class-calculus-1-2026-spring-a/refund-policy.md",
            "notes": "Operators may preview but not finalize operations wiki changes.",
        },
    )

    assert list_response.status_code == 200
    assert list_response.json()["meta"]["total"] == 1
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["available_actions"] == ["patch_preview"]
    assert preview_response.status_code == 200
    assert preview_response.json()["data"]["patch"]["operation"] == "update"
    assert approve_response.status_code == 403
    assert_api_error_envelope(
        approve_response,
        expected_code="forbidden_role",
        client_request_id="req-operator-review-approve",
    )
    assert_no_review_mutation_artifacts(
        settings,
        candidate_id=candidate.candidate_id,
        mutation_action="candidate_promoted",
        idempotency_key="idem-operator-review-approve",
        artifact_snapshot=artifact_snapshot,
    )


def test_students_cannot_access_review_endpoints(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_candidate(settings, "open-faq-homework-deadline.json")

    response = client.get(
        "/api/v1/review/candidates",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-student-review",
            domain="academic",
        ),
    )

    assert response.status_code == 403
    assert_api_error_envelope(
        response,
        expected_code="forbidden_role",
        client_request_id="req-student-review",
    )


def test_review_routes_emit_server_request_id_without_client_correlation_header(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_candidate(settings, "open-faq-homework-deadline.json")
    headers = build_headers(
        role="student",
        actor_id="stu-kim-minji",
        request_id="req-review-no-client-header",
        domain="academic",
    )
    headers.pop("X-Request-Id")

    response = client.get(
        "/api/v1/review/candidates",
        headers=headers,
    )

    assert response.status_code == 403
    assert_api_error_envelope(
        response,
        expected_code="forbidden_role",
    )


def test_review_routes_drop_invalid_client_correlation_header(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_candidate(settings, "open-faq-homework-deadline.json")

    response = client.get(
        "/api/v1/review/candidates",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="invalid request id",
            domain="academic",
        ),
    )

    assert response.status_code == 403
    assert_api_error_envelope(
        response,
        expected_code="forbidden_role",
    )


def test_review_routes_drop_multi_value_client_correlation_header_on_success_and_error(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_candidate(settings, "open-faq-homework-deadline.json")
    multi_value_request_id = "req-review-a, req-review-b"

    success_response = client.get(
        "/api/v1/review/candidates",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id=multi_value_request_id,
        ),
    )
    error_response = client.get(
        "/api/v1/review/candidates",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id=multi_value_request_id,
            domain="academic",
        ),
    )

    assert success_response.status_code == 200
    assert_server_owned_request_id(success_response, client_request_id=None)
    assert error_response.status_code == 403
    assert_api_error_envelope(
        error_response,
        expected_code="forbidden_role",
        client_request_id=None,
    )


def test_review_routes_drop_duplicated_client_correlation_headers_on_success_and_error(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_candidate(settings, "open-faq-homework-deadline.json")

    success_header_items = [
        *(
            (key, value)
            for key, value in build_headers(
                role="instructor",
                actor_id="ins-calculus-team",
                request_id="req-review-dup-a",
            ).items()
            if key != "X-Request-Id"
        ),
        ("X-Request-Id", "req-review-dup-a"),
        ("X-Request-Id", "req-review-dup-b"),
    ]
    error_header_items = [
        *(
            (key, value)
            for key, value in build_headers(
                role="student",
                actor_id="stu-kim-minji",
                request_id="req-review-dup-a",
                domain="academic",
            ).items()
            if key != "X-Request-Id"
        ),
        ("X-Request-Id", "req-review-dup-a"),
        ("X-Request-Id", "req-review-dup-b"),
    ]

    success_response = client.get(
        "/api/v1/review/candidates",
        headers=success_header_items,
    )
    error_response = client.get(
        "/api/v1/review/candidates",
        headers=error_header_items,
    )

    assert success_response.status_code == 200
    assert_server_owned_request_id(success_response, client_request_id=None)
    assert error_response.status_code == 403
    assert_api_error_envelope(
        error_response,
        expected_code="forbidden_role",
        client_request_id=None,
    )


def test_review_routes_echo_max_length_client_correlation_header(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_candidate(settings, "open-faq-homework-deadline.json")
    max_length_request_id = "a" * 128

    response = client.get(
        "/api/v1/review/candidates",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id=max_length_request_id,
        ),
    )

    assert response.status_code == 200
    assert_server_owned_request_id(
        response,
        client_request_id=max_length_request_id,
    )


def test_review_routes_drop_oversized_client_correlation_header(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_candidate(settings, "open-faq-homework-deadline.json")

    response = client.get(
        "/api/v1/review/candidates",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="a" * 129,
        ),
    )

    assert response.status_code == 200
    assert_server_owned_request_id(response, client_request_id=None)


def test_validator_can_list_cross_domain_candidates_and_finalize_operations_drop(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    academic_candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    operations_candidate = seed_candidate(settings, "open-operations-refund.json")

    list_response = client.get(
        "/api/v1/review/candidates",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-validator-review-list",
        ),
    )
    drop_response = client.post(
        f"/api/v1/review/candidates/{operations_candidate.candidate_id}/drop",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-validator-review-drop",
            idempotency_key="idem-validator-review-drop",
        ),
        json={
            "reason": "obsolete_operations_signal",
            "drop_notes": "Archive the low-value operations candidate after validator review.",
        },
    )

    assert list_response.status_code == 200
    assert {
        item["candidate_id"] for item in list_response.json()["data"]
    } == {academic_candidate.candidate_id, operations_candidate.candidate_id}
    assert {item["review_domain"] for item in list_response.json()["data"]} == {
        "academic",
        "operations",
    }
    assert drop_response.status_code == 200
    assert drop_response.json()["data"]["candidate"]["status"] == "dropped"


def test_system_can_preview_operations_candidate_in_review_domain(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    candidate = seed_candidate(settings, "open-operations-refund.json")
    seed_source_fixture(settings, "operations-refund-policy.md")
    seed_wiki_fixture(
        settings,
        source_filename="operations-refund-policy.seed.md",
        target_relative_path="wiki/operations/class-calculus-1-2026-spring-a/refund-policy.md",
    )

    response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/patch-preview",
        headers=build_headers(
            role="system",
            actor_id="system-review-bot",
            request_id="req-system-review-preview",
        ),
        json={
            "target_page_id": "page-operations-refund-policy",
            "target_path": "data/wiki/operations/class-calculus-1-2026-spring-a/refund-policy.md",
            "notes": "Preview validator-equivalent operations patch generation.",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["candidate"]["review_domain"] == "operations"
    assert payload["patch"]["target_page_id"] == "page-operations-refund-policy"
    assert payload["patch"]["operation"] == "update"


def test_system_cannot_finalize_review_mutations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.review as review_service

    client, settings = build_client(tmp_path)
    academic_candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    operations_candidate = seed_candidate(settings, "open-operations-refund.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_source_fixture(settings, "operations-refund-policy.md")
    seed_wiki_fixture(
        settings,
        source_filename="operations-refund-policy.seed.md",
        target_relative_path="wiki/operations/class-calculus-1-2026-spring-a/refund-policy.md",
    )
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )
    operations_snapshot = capture_review_artifact_snapshot(
        settings,
        candidates=(operations_candidate,),
        wiki_contract_paths=(
            "data/wiki/operations/class-calculus-1-2026-spring-a/refund-policy.md",
        ),
    )

    original_write_wiki_page = review_service._write_wiki_page
    failed_once = {"value": False}

    def flaky_write_wiki_page(path: Path, contents: str) -> None:
        if not failed_once["value"]:
            failed_once["value"] = True
            raise OSError("forced wiki write failure")
        original_write_wiki_page(path, contents)

    monkeypatch.setattr(review_service, "_write_wiki_page", flaky_write_wiki_page)

    instructor_approve_response = client.post(
        f"/api/v1/review/candidates/{academic_candidate.candidate_id}/approve",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-system-review-prime-pending",
            idempotency_key="idem-system-review-prime-pending",
        ),
        json={
            "target_page_id": "page-faq-homework-submission",
            "target_path": "data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
            "approval_notes": "Prime a pending sync state before the system tries to resume it.",
        },
    )

    assert instructor_approve_response.status_code == 500
    assert_api_error_envelope(
        instructor_approve_response,
        expected_code="internal_error",
        client_request_id="req-system-review-prime-pending",
    )
    promoted_candidate = get_candidate(settings, academic_candidate.candidate_id)
    assert promoted_candidate.status is CandidateStatus.PROMOTED
    assert promoted_candidate.wiki_sync_status is WikiSyncStatus.PENDING
    assert_client_request_id_not_persisted(
        settings,
        candidate=promoted_candidate,
        client_request_id="req-system-review-prime-pending",
        idempotency_key="idem-system-review-prime-pending",
        mutation_action="candidate_promoted",
        wiki_contract_path="data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )
    academic_snapshot = capture_review_artifact_snapshot(
        settings,
        candidates=(promoted_candidate,),
        wiki_contract_paths=(
            "data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
        ),
    )

    approve_response = client.post(
        f"/api/v1/review/candidates/{academic_candidate.candidate_id}/approve",
        headers=build_headers(
            role="system",
            actor_id="system-review-bot",
            request_id="req-system-review-approve",
            idempotency_key="idem-system-review-approve",
        ),
        json={
            "target_page_id": "page-faq-homework-submission",
            "target_path": "data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
            "approval_notes": "System should not finalize wiki promotion.",
        },
    )
    merge_response = client.post(
        f"/api/v1/review/candidates/{academic_candidate.candidate_id}/merge",
        headers=build_headers(
            role="system",
            actor_id="system-review-bot",
            request_id="req-system-review-merge",
            idempotency_key="idem-system-review-merge",
        ),
        json={
            "target_candidate_id": academic_candidate.candidate_id,
            "merge_notes": "System should not merge review candidates.",
        },
    )
    drop_response = client.post(
        f"/api/v1/review/candidates/{operations_candidate.candidate_id}/drop",
        headers=build_headers(
            role="system",
            actor_id="system-review-bot",
            request_id="req-system-review-drop",
            idempotency_key="idem-system-review-drop",
        ),
        json={
            "reason": "obsolete_operations_signal",
            "drop_notes": "System should not drop review candidates.",
        },
    )
    resume_response = client.post(
        f"/api/v1/review/candidates/{promoted_candidate.candidate_id}/resume-sync",
        headers=build_headers(
            role="system",
            actor_id="system-review-bot",
            request_id="req-system-review-resume",
            idempotency_key="idem-system-review-resume",
        ),
        json={
            "resume_notes": "System should not resume promotion attempts.",
        },
    )

    for response, client_request_id in (
        (approve_response, "req-system-review-approve"),
        (merge_response, "req-system-review-merge"),
        (drop_response, "req-system-review-drop"),
        (resume_response, "req-system-review-resume"),
    ):
        assert response.status_code == 403
        assert_api_error_envelope(
            response,
            expected_code="forbidden_role",
            client_request_id=client_request_id,
        )

    assert_no_review_mutation_artifacts(
        settings,
        candidate_id=academic_candidate.candidate_id,
        mutation_action="candidate_promoted",
        idempotency_key="idem-system-review-approve",
        artifact_snapshot=academic_snapshot,
    )
    assert_no_review_mutation_artifacts(
        settings,
        candidate_id=academic_candidate.candidate_id,
        mutation_action="candidate_merged",
        idempotency_key="idem-system-review-merge",
        artifact_snapshot=academic_snapshot,
    )
    assert_no_review_mutation_artifacts(
        settings,
        candidate_id=operations_candidate.candidate_id,
        mutation_action="candidate_dropped",
        idempotency_key="idem-system-review-drop",
        artifact_snapshot=operations_snapshot,
    )
    assert_no_review_mutation_artifacts(
        settings,
        candidate_id=promoted_candidate.candidate_id,
        mutation_action="candidate_wiki_sync_resumed",
        idempotency_key="idem-system-review-resume",
        artifact_snapshot=academic_snapshot,
    )


def test_system_review_endpoints_require_explicit_review_domain(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_candidate(settings, "open-operations-refund.json")
    headers = build_headers(
        role="system",
        actor_id="system-review-bot",
        request_id="req-system-review-missing-domain",
    )
    headers.pop("X-Knowloop-Domain")

    response = client.get(
        "/api/v1/review/candidates",
        headers=headers,
    )

    assert response.status_code == 422
    assert_api_error_envelope(
        response,
        expected_code="validation_failed",
        client_request_id="req-system-review-missing-domain",
    )
    details = response.json()["error"]["details"]
    assert details["role"] == "system"
    assert details["expected_domain"] == "review"


def test_instructor_review_endpoints_reject_review_domain_override(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_candidate(settings, "open-faq-homework-deadline.json")

    response = client.get(
        "/api/v1/review/candidates",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-instructor-review-domain-override",
            domain="review",
        ),
    )

    assert response.status_code == 422
    assert_api_error_envelope(
        response,
        expected_code="validation_failed",
        client_request_id="req-instructor-review-domain-override",
    )
