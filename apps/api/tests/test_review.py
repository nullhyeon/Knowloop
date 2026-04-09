import json
from datetime import datetime
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole, SourceType
from knowloop_api.core.frontmatter import parse_frontmatter_document
from knowloop_api.db.audit import list_audit_events
from knowloop_api.main import create_app
from knowloop_api.services.candidates import (
    CandidateItem,
    CandidateStatus,
    create_candidate,
    get_candidate,
)
from knowloop_api.services.sources import SourceRegistrationInput, register_source

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "data" / "fixtures"
REVIEW_SCHEMA_PATH = REPO_ROOT / "schemas" / "wiki_patch.json"


def build_settings(tmp_path: Path) -> Settings:
    return Settings(data_root=tmp_path / "d")


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
    payload = response.json()
    assert payload["meta"]["total"] == 2
    assert {item["kind"] for item in payload["data"]} == {"faq", "misconception"}
    assert all(item["review_domain"] == "academic" for item in payload["data"])


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


def test_review_patch_preview_matches_homework_fixture_contract(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("patch-preview-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/homework-submission.md",
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
            "target_path": "data/wiki/operations/refund-policy.md",
            "notes": "Reject mismatched page contract for operations wiki preview.",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_review_approve_promotes_candidate_and_writes_wiki_page(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    review_fixture = load_review_fixture("approve-homework-faq.json")
    candidate = seed_candidate(settings, "open-faq-homework-deadline.json")
    seed_source_fixture(settings, "announcement-homework-deadline.md")
    written_path = seed_wiki_fixture(
        settings,
        source_filename="faq-homework-submission.seed.md",
        target_relative_path="wiki/faq/homework-submission.md",
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
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    response_payload = first_response.json()["data"]
    stored_candidate = get_candidate(settings, candidate.candidate_id)
    assert response_payload["candidate"]["status"] == "promoted"
    assert stored_candidate.status is CandidateStatus.PROMOTED
    assert stored_candidate.approved_by == "ins-calculus-team"
    assert response_payload["wiki_page"]["page_id"] == review_fixture["expected"]["wiki_page_id"]

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
            "target_path": "data/wiki/faq/homework-submission.md",
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
        target_relative_path="wiki/faq/homework-submission.md",
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
    assert second_response.status_code == 422
    assert second_response.json()["error"]["code"] == "validation_failed"


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
        target_relative_path="wiki/faq/homework-submission.md",
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
    second_response = client.post(
        f"/api/v1/review/candidates/{candidate.candidate_id}/approve",
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 500
    assert second_response.status_code == 200
    assert get_candidate(settings, candidate.candidate_id).status is CandidateStatus.PROMOTED
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
    payload = response.json()["data"]
    assert payload["candidate"]["status"] == "merged"
    assert payload["candidate"]["merged_into"] == canonical_candidate.candidate_id
    assert payload["target_candidate"]["candidate_id"] == canonical_candidate.candidate_id
    assert "duplicate" in payload["target_candidate"]["tags"]


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
    assert response.json()["error"]["code"] == "invalid_request"


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
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
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
        headers=review_fixture["request_headers"],
        json=review_fixture["request_body"],
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["data"]["candidate"]["status"] == "dropped"

    drop_audit = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_dropped",
        idempotency_key="idem-fixture-drop-low-value",
    )
    assert len(drop_audit) == 1


def test_operator_can_list_operations_candidates_but_cannot_approve_them(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    candidate = seed_candidate(settings, "open-operations-refund.json")
    seed_source_fixture(settings, "operations-refund-policy.md")
    seed_wiki_fixture(
        settings,
        source_filename="operations-refund-policy.seed.md",
        target_relative_path="wiki/operations/refund-policy.md",
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
            "target_path": "data/wiki/operations/refund-policy.md",
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
            "target_path": "data/wiki/operations/refund-policy.md",
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
    assert approve_response.json()["error"]["code"] == "forbidden_scope"


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
    assert response.json()["error"]["code"] == "forbidden_scope"


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
        target_relative_path="wiki/operations/refund-policy.md",
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
            "target_path": "data/wiki/operations/refund-policy.md",
            "notes": "Preview validator-equivalent operations patch generation.",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["candidate"]["review_domain"] == "operations"
    assert payload["patch"]["target_page_id"] == "page-operations-refund-policy"
    assert payload["patch"]["operation"] == "update"


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

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_scope"
    assert response.json()["error"]["details"] == {"domain": None, "role": "system"}


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
    assert response.json()["error"]["code"] == "validation_failed"
