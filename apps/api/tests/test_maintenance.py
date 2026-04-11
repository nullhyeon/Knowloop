import hashlib
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import knowloop_api.services.candidates as candidate_service
from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole, SourceType
from knowloop_api.core.frontmatter import parse_frontmatter_document
from knowloop_api.db.bootstrap import bootstrap_storage
from knowloop_api.db.manifest import load_manifest
from knowloop_api.main import create_app
from knowloop_api.services.candidates import CandidateItem, create_candidate, find_candidate_path
from knowloop_api.services.maintenance import _wiki_file_path_class_scope
from knowloop_api.services.sources import (
    SourceRegistrationInput,
    register_source,
    resolve_source_path,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "data" / "fixtures"
STALE_CANDIDATE_ID = "cand-misconception-class-calculus-1-2026-spring-a-old-signal-20260301T090000Z"
CHAIN_RULE_SOURCE_ID = "src-lecture-note-class-calculus-1-2026-spring-a-week-03-20260408T103000Z"


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
                STALE_CANDIDATE_ID
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
                        CHAIN_RULE_SOURCE_ID
                    ),
                    "source_type": "lecture_note",
                }
            ],
            "session_refs": [],
            "created_at": "2026-03-01T09:00:00Z",
            "updated_at": "2026-03-01T09:00:00Z",
        }
    )
    create_candidate(
        settings,
        stale_candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        request_id="req-seed-maintenance-candidate",
    )

    wiki_path = (
        settings.data_root
        / "wiki"
        / "faq"
        / "class-calculus-1-2026-spring-a"
        / "maintenance-drift.md"
    )
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
        "wiki_layout_issues": 0,
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
    assert payload["checks"]
    assert all("entity_id" not in check for check in payload["checks"])
    assert all("details" not in check for check in payload["checks"])
    assert all("message" not in check for check in payload["checks"])
    assert all("summary" in check for check in payload["checks"])


def test_maintenance_status_exposes_full_check_shape_to_validator(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-prime-validator-shape",
            domain="review",
        ),
    )
    response = client.get(
        "/api/v1/maintenance/status",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-status-validator-shape",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["checks"]
    assert all("entity_id" in check for check in payload["checks"])
    assert all("details" in check for check in payload["checks"])


def test_maintenance_status_allows_system_with_sensitive_checks(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-prime-system-shape",
            domain="review",
        ),
    )
    response = client.get(
        "/api/v1/maintenance/status",
        headers=build_headers(
            role="system",
            actor_id="system-runtime",
            request_id="req-maintenance-status-system-shape",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["checks"]
    assert all("entity_id" in check for check in payload["checks"])
    assert all("details" in check for check in payload["checks"])


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
    assert "last_run_at" not in payload
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


def test_maintenance_status_rejects_persisted_report_with_mismatched_scope(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    report_path = (
        settings.meta_root
        / "maintenance"
        / "course-calculus-1"
        / "class-calculus-1-2026-spring-a"
        / "lint-status.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        """{
  "version": 1,
  "course_id": "course-other",
  "class_id": "class-other",
  "status": "clean",
  "health_score": 100,
  "review_queue_count": 0,
  "summary": {
    "errors": 0,
    "warnings": 0,
    "stale_candidates": 0,
    "orphan_candidate_refs": 0,
    "orphan_source_refs": 0
  },
  "checks": []
}
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/status",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-status-mismatched-scope",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["course_id"] == "course-calculus-1"
    assert payload["class_id"] == "class-calculus-1-2026-spring-a"
    assert payload["status"] == "error"
    assert payload["review_queue_count"] == 1
    assert payload["checks"][0]["code"] == "maintenance_report_unreadable"
    assert payload["checks"][0]["entity_id"] == "course-calculus-1:class-calculus-1-2026-spring-a"


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


def test_maintenance_status_rejects_wrong_domain_for_instructor(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    response = client.get(
        "/api/v1/maintenance/status",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-maintenance-status-instructor-wrong-domain",
            domain="review",
        ),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_maintenance_status_rejects_wrong_domain_for_validator(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    response = client.get(
        "/api/v1/maintenance/status",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-status-validator-wrong-domain",
            domain="academic",
        ),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_scope"


def test_maintenance_status_rejects_wrong_domain_for_system(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    response = client.get(
        "/api/v1/maintenance/status",
        headers=build_headers(
            role="system",
            actor_id="system-runtime",
            request_id="req-maintenance-status-system-wrong-domain",
            domain="academic",
        ),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_scope"


def test_maintenance_report_uses_candidate_updated_at_for_staleness(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)
    stale_candidate_path = find_candidate_path(settings, STALE_CANDIDATE_ID)
    stale_payload = json.loads(stale_candidate_path.read_text(encoding="utf-8"))
    stale_payload["updated_at"] = "2026-04-09T09:00:00Z"
    stale_candidate_path.write_text(
        json.dumps(stale_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-fresh-updated-at",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert {check["code"] for check in payload["checks"]} == {
        "orphan_wiki_candidate_ref",
        "orphan_wiki_source_ref",
    }
    assert payload["summary"]["stale_candidates"] == 0
    assert payload["summary"]["warnings"] == 0


def test_maintenance_report_uses_created_at_when_legacy_candidate_lacks_updated_at(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)
    stale_candidate_path = find_candidate_path(settings, STALE_CANDIDATE_ID)
    stale_payload = json.loads(stale_candidate_path.read_text(encoding="utf-8"))
    stale_payload.pop("updated_at", None)
    stale_candidate_path.write_text(
        json.dumps(stale_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-legacy-candidate-updated-at",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    stale_checks = [
        check
        for check in payload["checks"]
        if check["code"] == "stale_candidate"
        and check["entity_id"] == STALE_CANDIDATE_ID
    ]
    assert len(stale_checks) == 1
    reloaded_payload = json.loads(stale_candidate_path.read_text(encoding="utf-8"))
    assert reloaded_payload["updated_at"] == stale_payload["created_at"]


def test_maintenance_report_uses_created_at_when_legacy_candidate_lock_blocks_rewrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)
    stale_candidate_path = find_candidate_path(settings, STALE_CANDIDATE_ID)
    stale_payload = json.loads(stale_candidate_path.read_text(encoding="utf-8"))
    stale_payload.pop("updated_at", None)
    stale_candidate_path.write_text(
        json.dumps(stale_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    original_acquire_locks = candidate_service._acquire_candidate_locks

    def flaky_locks(paths):  # noqa: ANN001, ANN202
        if stale_candidate_path in paths:
            raise candidate_service.CandidateStateError("candidate changed during transition")
        return original_acquire_locks(paths)

    monkeypatch.setattr(candidate_service, "_acquire_candidate_locks", flaky_locks)

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-legacy-candidate-lock-contention",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    stale_checks = [
        check
        for check in payload["checks"]
        if check["code"] == "stale_candidate"
        and check["entity_id"] == STALE_CANDIDATE_ID
    ]
    assert len(stale_checks) == 1
    reloaded_payload = json.loads(stale_candidate_path.read_text(encoding="utf-8"))
    assert "updated_at" not in reloaded_payload


def test_maintenance_report_flags_manifest_source_with_missing_file(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
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
    manifest = load_manifest(settings)
    source_record = next(source for source in manifest.sources)
    resolve_source_path(settings, source_record.origin_path).unlink()

    wiki_path = (
        settings.data_root
        / "wiki"
        / "concepts"
        / "class-calculus-1-2026-spring-a"
        / "existing-source-missing-file.md"
    )
    wiki_path.parent.mkdir(parents=True, exist_ok=True)
    wiki_path.write_text(
        f"""---
page_id: page-concepts-existing-source-missing-file
domain: concepts
title: Existing Source Missing File
course_id: course-calculus-1
class_scope: class-calculus-1-2026-spring-a
updated_at: 2026-04-08T10:40:00Z
source_refs: ["{source_record.source_id}"]
candidate_refs: []
summary: A wiki page used to verify missing manifest-backed source files.
---

# Existing Source Missing File

This page intentionally references a manifest source whose file is gone.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-missing-source-file",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    matching_checks = [
        check
        for check in payload["checks"]
        if check["code"] == "orphan_wiki_source_ref"
        and check["details"]["missing_source_id"] == source_record.source_id
    ]
    assert len(matching_checks) == 1
    assert matching_checks[0]["entity_id"] == "page-concepts-existing-source-missing-file"


def test_maintenance_report_flags_manifest_source_path_that_became_directory(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
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
    manifest = load_manifest(settings)
    source_record = next(source for source in manifest.sources)
    source_path = resolve_source_path(settings, source_record.origin_path)
    source_path.unlink()
    source_path.mkdir(parents=True, exist_ok=True)

    wiki_path = (
        settings.data_root
        / "wiki"
        / "concepts"
        / "class-calculus-1-2026-spring-a"
        / "existing-source-directory-drift.md"
    )
    wiki_path.parent.mkdir(parents=True, exist_ok=True)
    wiki_path.write_text(
        f"""---
page_id: page-concepts-existing-source-directory-drift
domain: concepts
title: Existing Source Directory Drift
course_id: course-calculus-1
class_scope: class-calculus-1-2026-spring-a
updated_at: 2026-04-08T10:40:00Z
source_refs: ["{source_record.source_id}"]
candidate_refs: []
summary: A wiki page used to verify that directories do not count as backing source files.
---

# Existing Source Directory Drift

This page intentionally references a manifest source whose file path now points to a directory.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-source-directory-drift",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    matching_checks = [
        check
        for check in payload["checks"]
        if check["code"] == "orphan_wiki_source_ref"
        and check["details"]["missing_source_id"] == source_record.source_id
    ]
    assert len(matching_checks) == 1
    assert matching_checks[0]["entity_id"] == "page-concepts-existing-source-directory-drift"


def test_maintenance_report_reads_authoritative_wiki_store_after_out_of_band_add(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    warmup_response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-authoritative-warmup",
            domain="review",
        ),
    )
    assert warmup_response.status_code == 200

    additional_wiki_path = (
        settings.data_root
        / "wiki"
        / "faq"
        / "class-calculus-1-2026-spring-a"
        / "maintenance-authoritative-extra.md"
    )
    additional_wiki_path.parent.mkdir(parents=True, exist_ok=True)
    additional_wiki_path.write_text(
        """---
page_id: page-faq-maintenance-authoritative-extra
domain: faq
title: Maintenance Authoritative Extra
course_id: course-calculus-1
class_scope: class-calculus-1-2026-spring-a
updated_at: 2026-04-08T10:55:00Z
source_refs: []
candidate_refs: ["cand-missing-maintenance-candidate-authoritative-extra"]
summary: Added after the scoped index exists to verify authoritative wiki scanning.
---

# Maintenance Authoritative Extra

This page is written outside the review flow after the scoped maintenance index already exists.
""",
        encoding="utf-8",
    )

    second_report = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-authoritative-scan",
            domain="review",
        ),
    )

    assert second_report.status_code == 200
    payload = second_report.json()["data"]
    orphan_candidate_page_ids = {
        check["entity_id"]
        for check in payload["checks"]
        if check["code"] == "orphan_wiki_candidate_ref"
    }
    assert orphan_candidate_page_ids == {
        "page-faq-maintenance-authoritative-extra",
        "page-faq-maintenance-drift",
    }


def test_maintenance_report_surfaces_noncanonical_wiki_page_paths(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    legacy_path = settings.data_root / "wiki" / "faq" / "legacy-homework-submission.md"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        """---
page_id: page-faq-legacy-homework-submission
domain: faq
title: Legacy Homework Submission
course_id: course-calculus-1
class_scope: class-calculus-1-2026-spring-a
updated_at: 2026-04-08T11:05:00Z
source_refs: []
candidate_refs: []
summary: Legacy unscoped wiki file that now needs migration.
---

# Legacy Homework Submission

This page intentionally lives outside the canonical class-scoped path.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-legacy-wiki-path",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    matching_checks = [
        check
        for check in payload["checks"]
        if check["code"] == "noncanonical_wiki_page_path"
        and check["entity_id"] == "page-faq-legacy-homework-submission"
    ]
    assert len(matching_checks) == 1
    assert matching_checks[0]["details"]["path"].endswith("wiki/faq/legacy-homework-submission.md")
    assert matching_checks[0]["details"]["canonical_path"].endswith(
        "wiki/faq/class-calculus-1-2026-spring-a/legacy-homework-submission.md"
    )
    assert payload["summary"]["wiki_layout_issues"] == 1


def test_maintenance_report_surfaces_partial_scope_legacy_wiki_file(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    legacy_path = settings.data_root / "wiki" / "faq" / "broken-legacy-homework-page.md"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        """---
page_id page-faq-broken-legacy-homework-page
domain: faq
class_scope: class-calculus-1-2026-spring-a
---

# Broken Legacy Homework Page

This legacy unscoped file has unreadable frontmatter but still exposes class scope.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-broken-legacy-unscoped",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    matching_checks = [
        check
        for check in payload["checks"]
        if check["code"] == "invalid_wiki_page_metadata"
        and check["entity_id"].endswith("wiki/faq/broken-legacy-homework-page.md")
    ]
    assert len(matching_checks) == 1
    assert "unsupported frontmatter line" in matching_checks[0]["details"]["reason"]
    assert payload["summary"]["wiki_layout_issues"] == 1


def test_maintenance_report_surfaces_unterminated_legacy_wiki_file_with_class_scope(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    legacy_path = settings.data_root / "wiki" / "faq" / "broken-legacy-open-frontmatter-page.md"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        """---
page_id: page-faq-broken-legacy-open-frontmatter-page
domain: faq
class_scope: class-calculus-1-2026-spring-a

# Broken Legacy Open Frontmatter Page

This legacy unscoped file never closes its frontmatter block.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-broken-legacy-open-frontmatter",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    matching_checks = [
        check
        for check in payload["checks"]
        if check["code"] == "invalid_wiki_page_metadata"
        and check["entity_id"] == "page-faq-broken-legacy-open-frontmatter-page"
    ]
    assert len(matching_checks) == 1
    assert matching_checks[0]["details"]["path"].endswith(
        "wiki/faq/broken-legacy-open-frontmatter-page.md"
    )
    assert payload["summary"]["wiki_layout_issues"] == 1


def test_maintenance_report_skips_unreadable_legacy_wiki_when_course_drifted(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    legacy_path = settings.data_root / "wiki" / "faq" / "broken-legacy-class-wins-page.md"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        """---
page_id page-faq-broken-legacy-class-wins-page
domain: faq
course_id: course-other
class_scope: class-calculus-1-2026-spring-a
---

# Broken Legacy Class Wins Page

This legacy unscoped file keeps the class scope but has stale course metadata.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-broken-legacy-class-wins",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert all(
        check["entity_id"] != "wiki/faq/broken-legacy-class-wins-page.md"
        for check in payload["checks"]
    )
    assert all(
        check["entity_id"] != "page-faq-broken-legacy-class-wins-page"
        for check in payload["checks"]
    )


def test_maintenance_report_skips_readable_legacy_wiki_when_course_drifted(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    legacy_path = settings.data_root / "wiki" / "faq" / "legacy-readable-class-wins-page.md"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        """---
page_id: page-faq-legacy-readable-class-wins-page
domain: faq
title: Legacy Readable Class Wins Page
course_id: course-other
class_scope: class-calculus-1-2026-spring-a
updated_at: 2026-04-08T11:30:00Z
summary: Readable legacy page with drifted course metadata.
source_refs: []
candidate_refs: []
---

# Legacy Readable Class Wins Page

This readable legacy unscoped file keeps the class scope but has stale course metadata.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-readable-legacy-class-wins",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert all(
        check["entity_id"] != "page-faq-legacy-readable-class-wins-page"
        for check in payload["checks"]
    )
    assert all(
        check["entity_id"] != "wiki/faq/legacy-readable-class-wins-page.md"
        for check in payload["checks"]
    )


def test_maintenance_report_skips_legacy_body_scope_contamination(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    legacy_path = settings.data_root / "wiki" / "faq" / "broken-legacy-body-scope-page.md"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        """---
page_id page-faq-broken-legacy-body-scope-page
domain: faq

# Broken Legacy Body Scope Page

class_scope: class-calculus-1-2026-spring-a
This legacy file should not become attributable from body text.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-broken-legacy-body-scope",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert all(
        check["entity_id"] != "wiki/faq/broken-legacy-body-scope-page.md"
        for check in payload["checks"]
    )
    assert all(
        check["entity_id"] != "page-faq-broken-legacy-body-scope-page"
        for check in payload["checks"]
    )


def test_maintenance_report_skips_unclosed_partial_frontmatter_body_scope_contamination(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    legacy_path = (
        settings.data_root / "wiki" / "faq" / "broken-legacy-open-body-scope-page.md"
    )
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        """---
domain: faq
class_scope: class-calculus-1-2026-spring-a
This body line should prevent partial scope attribution.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-open-body-scope",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert all(
        check["entity_id"] != "wiki/faq/broken-legacy-open-body-scope-page.md"
        for check in payload["checks"]
    )


def test_maintenance_report_skips_unattributable_legacy_wiki_file(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    legacy_path = settings.data_root / "wiki" / "faq" / "broken-legacy-no-scope-page.md"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        """---
page_id page-faq-broken-legacy-no-scope-page
domain faq
title Broken Legacy No Scope Page
---

# Broken Legacy No Scope Page

This legacy unscoped file has unreadable frontmatter and no recoverable scope metadata.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-broken-legacy-no-scope",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert all(
        check["entity_id"] != "wiki/faq/broken-legacy-no-scope-page.md"
        for check in payload["checks"]
    )
    assert all(
        check["entity_id"] != "page-faq-broken-legacy-no-scope-page"
        for check in payload["checks"]
    )


def test_maintenance_report_skips_course_only_legacy_wiki_file(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    legacy_path = settings.data_root / "wiki" / "faq" / "broken-legacy-course-only-page.md"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        """---
page_id page-faq-broken-legacy-course-only-page
domain: faq
course_id: course-calculus-1
---

# Broken Legacy Course Only Page

This legacy unscoped file only exposes course scope and should not leak across classes.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-broken-legacy-course-only",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert all(
        check["entity_id"] != "wiki/faq/broken-legacy-course-only-page.md"
        for check in payload["checks"]
    )
    assert all(
        check["entity_id"] != "page-faq-broken-legacy-course-only-page"
        for check in payload["checks"]
    )


def test_maintenance_report_does_not_overattribute_unreadable_legacy_file_with_other_scope(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    legacy_path = settings.data_root / "wiki" / "faq" / "broken-other-scope-homework-page.md"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        """---
page_id page-faq-broken-other-scope-homework-page
domain: faq
course_id: course-other
class_scope: class-other
---

# Broken Other Scope Homework Page

This unreadable legacy file belongs to another scope and should not leak here.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-broken-legacy-other-scope",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert all(
        check["entity_id"] != "wiki/faq/broken-other-scope-homework-page.md"
        for check in payload["checks"]
    )
    assert all(
        check["entity_id"] != "page-faq-broken-other-scope-homework-page"
        for check in payload["checks"]
    )


def test_maintenance_report_surfaces_invalid_wiki_metadata(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    malformed_path = (
        settings.data_root
        / "wiki"
        / "faq"
        / "class-calculus-1-2026-spring-a"
        / "broken-homework-page.md"
    )
    malformed_path.parent.mkdir(parents=True, exist_ok=True)
    malformed_path.write_text(
        """---
page_id: page-concepts-broken-homework-page
domain: faq
title: Broken Homework Page
course_id: course-calculus-1
class_scope: class-calculus-1-2026-spring-a
updated_at: 2026-04-08T11:10:00Z
source_refs: []
candidate_refs: []
summary: Metadata intentionally violates the page_id/domain contract.
---

# Broken Homework Page

This page should surface as a repair-needed wiki metadata issue.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-invalid-wiki-metadata",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    matching_checks = [
        check
        for check in payload["checks"]
        if check["code"] == "invalid_wiki_page_metadata"
        and check["entity_id"] == "page-concepts-broken-homework-page"
    ]
    assert len(matching_checks) == 1
    assert matching_checks[0]["details"]["path"].endswith(
        "wiki/faq/class-calculus-1-2026-spring-a/broken-homework-page.md"
    )
    assert "page-faq-<slug>" in matching_checks[0]["details"]["reason"]
    assert payload["summary"]["wiki_layout_issues"] == 1


def test_maintenance_report_surfaces_path_owned_wiki_with_mismatched_scope_metadata(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    mismatched_path = (
        settings.data_root
        / "wiki"
        / "faq"
        / "class-calculus-1-2026-spring-a"
        / "wrong-scope-homework-page.md"
    )
    mismatched_path.parent.mkdir(parents=True, exist_ok=True)
    mismatched_path.write_text(
        """---
page_id: page-faq-wrong-scope-homework-page
domain: faq
title: Wrong Scope Homework Page
course_id: course-other
class_scope: class-other
updated_at: 2026-04-08T11:10:00Z
source_refs: []
candidate_refs: []
summary: Metadata intentionally points away from the class-scoped directory that owns this file.
---

# Wrong Scope Homework Page

This page should surface because its directory belongs to the current class
while its metadata does not.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-path-owned-wrong-scope",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    matching_checks = [
        check
        for check in payload["checks"]
        if check["code"] == "invalid_wiki_page_metadata"
        and check["entity_id"] == "page-faq-wrong-scope-homework-page"
    ]
    assert len(matching_checks) == 1
    assert matching_checks[0]["details"]["path"].endswith(
        "wiki/faq/class-calculus-1-2026-spring-a/wrong-scope-homework-page.md"
    )
    assert "course_id points to" in matching_checks[0]["details"]["reason"]
    assert "class_scope points to" in matching_checks[0]["details"]["reason"]
    assert payload["summary"]["wiki_layout_issues"] == 1


def test_maintenance_report_does_not_surface_other_class_path_owned_wiki_to_claimed_scope(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    misplaced_path = (
        settings.data_root
        / "wiki"
        / "faq"
        / "class-calculus-1-2026-spring-b"
        / "claimed-by-class-a-homework-page.md"
    )
    misplaced_path.parent.mkdir(parents=True, exist_ok=True)
    misplaced_path.write_text(
        """---
page_id: page-faq-claimed-by-class-a-homework-page
domain: faq
title: Claimed By Class A Homework Page
course_id: course-calculus-1
class_scope: class-calculus-1-2026-spring-a
updated_at: 2026-04-08T11:10:00Z
source_refs: []
candidate_refs: []
summary: Metadata claims class A even though the file lives under class B.
---

# Claimed By Class A Homework Page

This page should stay invisible to class A because class B owns the path.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-claimed-by-class-a",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert all(
        check["entity_id"] != "page-faq-claimed-by-class-a-homework-page"
        for check in payload["checks"]
    )


def test_maintenance_report_surfaces_unreadable_scoped_wiki_frontmatter(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    malformed_path = (
        settings.data_root
        / "wiki"
        / "faq"
        / "class-calculus-1-2026-spring-a"
        / "broken-frontmatter-page.md"
    )
    malformed_path.parent.mkdir(parents=True, exist_ok=True)
    malformed_path.write_text(
        """---
page_id page-faq-broken-frontmatter-page
domain: faq
course_id: course-calculus-1
class_scope: class-calculus-1-2026-spring-a
---

# Broken Frontmatter Page

This page has unreadable frontmatter syntax.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-broken-frontmatter",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    matching_checks = [
        check
        for check in payload["checks"]
        if check["code"] == "invalid_wiki_page_metadata"
        and check["entity_id"].endswith(
            "wiki/faq/class-calculus-1-2026-spring-a/broken-frontmatter-page.md"
        )
    ]
    assert len(matching_checks) == 1
    assert "unsupported frontmatter line" in matching_checks[0]["details"]["reason"]
    assert payload["summary"]["wiki_layout_issues"] == 1


def test_maintenance_report_surfaces_path_owned_unreadable_wiki_with_wrong_scope_metadata(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    malformed_path = (
        settings.data_root
        / "wiki"
        / "faq"
        / "class-calculus-1-2026-spring-a"
        / "broken-wrong-scope-frontmatter-page.md"
    )
    malformed_path.parent.mkdir(parents=True, exist_ok=True)
    malformed_path.write_text(
        """---
page_id page-faq-broken-wrong-scope-frontmatter-page
domain: faq
course_id: course-other
class_scope: class-other
---

# Broken Wrong Scope Frontmatter Page

This page lives in the current class path but its frontmatter is unreadable
and points to another scope.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-broken-wrong-scope-frontmatter",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    matching_checks = [
        check
        for check in payload["checks"]
        if check["code"] == "invalid_wiki_page_metadata"
        and check["entity_id"].endswith(
            "wiki/faq/class-calculus-1-2026-spring-a/broken-wrong-scope-frontmatter-page.md"
        )
    ]
    assert len(matching_checks) == 1
    assert "unsupported frontmatter line" in matching_checks[0]["details"]["reason"]
    assert payload["summary"]["wiki_layout_issues"] == 1


def test_maintenance_report_surfaces_wiki_read_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import knowloop_api.services.maintenance as maintenance_service

    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)
    unreadable_path = (
        settings.data_root
        / "wiki"
        / "faq"
        / "class-calculus-1-2026-spring-a"
        / "maintenance-drift.md"
    )
    original_load = maintenance_service.load_wiki_page_from_path

    def flaky_load(path: Path):  # noqa: ANN202
        if path.resolve() == unreadable_path.resolve():
            raise PermissionError("forced wiki read failure")
        return original_load(path)

    monkeypatch.setattr(maintenance_service, "load_wiki_page_from_path", flaky_load)

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-unreadable-wiki-read",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    matching_checks = [
        check
        for check in payload["checks"]
        if check["code"] == "invalid_wiki_page_metadata"
        and check["entity_id"] == "page-faq-maintenance-drift"
    ]
    assert len(matching_checks) == 1
    assert "forced wiki read failure" in matching_checks[0]["details"]["reason"]
    assert payload["summary"]["wiki_layout_issues"] == 1


def test_maintenance_report_surfaces_binary_corrupted_wiki_file(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_maintenance_runtime(settings)

    corrupted_path = (
        settings.data_root
        / "wiki"
        / "faq"
        / "class-calculus-1-2026-spring-a"
        / "binary-corrupted-page.md"
    )
    corrupted_path.parent.mkdir(parents=True, exist_ok=True)
    corrupted_path.write_bytes(b"\xff\xfe\x00\x81not-utf8")

    response = client.get(
        "/api/v1/maintenance/report",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-maintenance-report-binary-corrupted-wiki",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    matching_checks = [
        check
        for check in payload["checks"]
        if check["code"] == "invalid_wiki_page_metadata"
        and check["entity_id"].endswith(
            "wiki/faq/class-calculus-1-2026-spring-a/binary-corrupted-page.md"
        )
    ]
    assert len(matching_checks) == 1
    assert payload["summary"]["wiki_layout_issues"] == 1


def test_wiki_file_path_class_scope_prefers_deepest_wiki_segment(tmp_path: Path) -> None:
    path = (
        tmp_path
        / "wiki"
        / "workspace"
        / "data"
        / "wiki"
        / "faq"
        / "class-calculus-1-2026-spring-a"
        / "example.md"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# placeholder\n", encoding="utf-8")

    assert _wiki_file_path_class_scope(path) == "class-calculus-1-2026-spring-a"


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
