import hashlib
import os
import shutil
import sqlite3
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import knowloop_api.services.sources as source_service
from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole, RequestDomain, SourceType
from knowloop_api.db.audit import get_mutation_request, list_audit_events
from knowloop_api.db.bootstrap import bootstrap_storage
from knowloop_api.db.manifest import load_manifest
from knowloop_api.main import create_app
from knowloop_api.services.sources import (
    SourceRegistrationInput,
    SourceStateError,
    get_source,
    register_source,
    resolve_source_path,
)


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
    request_id: str = "req-test-source",
    idempotency_key: str | None = None,
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
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def assert_server_owned_request_id(
    response,
    *,
    client_request_id: str | None,
) -> None:
    payload = response.json()
    assert payload["request_id"]
    assert response.headers["X-Request-Id"] == payload["request_id"]
    if client_request_id is not None:
        assert payload["request_id"] != client_request_id


def test_register_source_endpoint_persists_raw_file_manifest_and_audit(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)

    response = client.post(
        "/api/v1/sources/register",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-source-register",
            idempotency_key="idem-source-register",
        ),
        json={
            "source_type": "lecture_note",
            "title": "Week 03 Chain Rule",
            "content": "# Chain Rule\nUse the outer derivative after the inner derivative.",
            "mime_type": "text/markdown",
            "filename": "week-03-chain-rule.md",
            "tags": ["week-03", "chain-rule"],
        },
    )

    payload = response.json()
    assert response.status_code == 201
    assert_server_owned_request_id(response, client_request_id="req-source-register")
    assert payload["data"]["source_type"] == "lecture_note"
    assert payload["data"]["status"] == "registered"
    assert payload["data"]["stored_path"].startswith(
        "data/raw/lecture-note/class-calculus-1-2026-spring-a/"
    )

    stored_source = get_source(settings, payload["data"]["source_id"])
    stored_path = resolve_source_path(settings, stored_source.origin_path)
    manifest = load_manifest(settings)
    audit_events = list_audit_events(
        settings,
        entity_type="source",
        entity_id=stored_source.source_id,
    )

    assert stored_path.read_text(encoding="utf-8").startswith("# Chain Rule")
    assert manifest.sources[0].source_id == stored_source.source_id
    assert audit_events[0].action == "source_registered"
    assert audit_events[0].idempotency_key == "idem-source-register"


def test_register_source_endpoint_uses_server_owned_request_ids(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.post(
        "/api/v1/sources/register",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-client-supplied-source",
            idempotency_key="idem-source-server-owned-request-id",
        ),
        json={
            "source_type": "lecture_note",
            "title": "Week 03 Chain Rule",
            "content": "# Chain Rule\nUse the outer derivative after the inner derivative.",
            "mime_type": "text/markdown",
            "filename": "week-03-chain-rule.md",
        },
    )

    assert response.status_code == 201
    assert_server_owned_request_id(response, client_request_id="req-client-supplied-source")


def test_register_source_endpoint_replay_uses_attempt_local_request_ids(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)
    headers = build_headers(
        role="instructor",
        actor_id="ins-calculus-team",
        request_id="req-client-supplied-source-replay",
        idempotency_key="idem-source-http-replay",
    )
    body = {
        "source_type": "lecture_note",
        "title": "Week 03 Chain Rule",
        "content": "# Chain Rule\nUse the outer derivative after the inner derivative.",
        "mime_type": "text/markdown",
        "filename": "week-03-chain-rule.md",
    }

    first_response = client.post("/api/v1/sources/register", headers=headers, json=body)
    second_response = client.post("/api/v1/sources/register", headers=headers, json=body)

    first_payload = first_response.json()
    second_payload = second_response.json()

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_payload["data"] == second_payload["data"]
    assert first_payload["data"]["source_id"] == second_payload["data"]["source_id"]
    assert first_payload["request_id"] != second_payload["request_id"]
    assert_server_owned_request_id(
        first_response,
        client_request_id="req-client-supplied-source-replay",
    )
    assert_server_owned_request_id(
        second_response,
        client_request_id="req-client-supplied-source-replay",
    )


def test_register_source_is_idempotent_with_same_key(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    registration = SourceRegistrationInput(
        source_type=SourceType.LECTURE_NOTE,
        title="Week 03 Chain Rule",
        content="# Chain Rule\nA compact note.",
        mime_type="text/markdown",
        filename="week-03-chain-rule.md",
        tags=["week-03", "chain-rule"],
    )

    first_result = register_source(
        settings,
        registration,
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        idempotency_key="idem-source-same",
        created_at=datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
    )
    second_result = register_source(
        settings,
        registration,
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        idempotency_key="idem-source-same",
        created_at=datetime(2026, 4, 8, 10, 31, tzinfo=UTC),
    )

    manifest = load_manifest(settings)
    audit_events = list_audit_events(
        settings,
        entity_type="source",
        action="source_registered",
        idempotency_key="idem-source-same",
    )

    assert second_result == first_result
    assert len(manifest.sources) == 1
    assert len(audit_events) == 1


def test_register_source_serializes_overlapping_idempotent_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    registration = SourceRegistrationInput(
        source_type=SourceType.LECTURE_NOTE,
        title="Week 03 Chain Rule",
        content="# Chain Rule\nA compact note.",
        mime_type="text/markdown",
        filename="week-03-chain-rule.md",
        tags=["week-03", "chain-rule"],
    )
    original_acquire_locks = source_service._acquire_locks
    first_lock_entered = threading.Event()
    release_first_lock = threading.Event()
    acquire_calls = {"count": 0}

    def blocking_acquire_locks(paths):  # noqa: ANN001
        lock_paths = original_acquire_locks(paths)
        acquire_calls["count"] += 1
        if acquire_calls["count"] == 1:
            first_lock_entered.set()
            assert release_first_lock.wait(timeout=5)
        return lock_paths

    monkeypatch.setattr(source_service, "_acquire_locks", blocking_acquire_locks)

    results: list[object] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            results.append(
                register_source(
                    settings,
                    registration,
                    course_id="course-calculus-1",
                    class_id="class-calculus-1-2026-spring-a",
                    actor_role=ActorRole.INSTRUCTOR,
                    actor_id="ins-calculus-team",
                    idempotency_key="idem-source-overlap",
                    created_at=datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
                )
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    first_thread = threading.Thread(target=worker)
    second_thread = threading.Thread(target=worker)

    first_thread.start()
    assert first_lock_entered.wait(timeout=5)
    second_thread.start()
    release_first_lock.set()

    first_thread.join(timeout=5)
    second_thread.join(timeout=5)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert not errors
    assert len(results) == 2
    assert results[0] == results[1]
    assert acquire_calls["count"] == 1


def test_register_source_serializes_unrelated_parallel_registrations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    original_acquire_locks = source_service._acquire_locks
    first_lock_entered = threading.Event()
    release_first_lock = threading.Event()
    acquire_calls = {"count": 0}

    def blocking_acquire_locks(paths):  # noqa: ANN001
        lock_paths = original_acquire_locks(paths)
        acquire_calls["count"] += 1
        if acquire_calls["count"] == 1:
            first_lock_entered.set()
            assert release_first_lock.wait(timeout=5)
        return lock_paths

    monkeypatch.setattr(source_service, "_acquire_locks", blocking_acquire_locks)

    results: list[object] = []
    errors: list[BaseException] = []

    def worker(registration: SourceRegistrationInput, idempotency_key: str) -> None:
        try:
            results.append(
                register_source(
                    settings,
                    registration,
                    course_id="course-calculus-1",
                    class_id="class-calculus-1-2026-spring-a",
                    actor_role=ActorRole.INSTRUCTOR,
                    actor_id="ins-calculus-team",
                    idempotency_key=idempotency_key,
                    created_at=datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
                )
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    first_thread = threading.Thread(
        target=worker,
        args=(
            SourceRegistrationInput(
                source_type=SourceType.LECTURE_NOTE,
                title="Week 03 Chain Rule",
                content="# Chain Rule\nVariant A.",
                mime_type="text/markdown",
                filename="chain-rule-a.md",
            ),
            "idem-source-parallel-a",
        ),
    )
    second_thread = threading.Thread(
        target=worker,
        args=(
            SourceRegistrationInput(
                source_type=SourceType.LECTURE_NOTE,
                title="Week 04 Product Rule",
                content="# Product Rule\nVariant B.",
                mime_type="text/markdown",
                filename="product-rule-b.md",
            ),
            "idem-source-parallel-b",
        ),
    )

    first_thread.start()
    assert first_lock_entered.wait(timeout=5)
    second_thread.start()
    release_first_lock.set()

    first_thread.join(timeout=5)
    second_thread.join(timeout=5)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert not errors
    assert len(results) == 2
    assert results[0] != results[1]
    assert acquire_calls["count"] == 2


def test_register_source_preserves_raw_content_bytes(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    original_content = "  # Chain Rule\nUse the outer derivative after the inner derivative.\n"
    source_record = register_source(
        settings,
        SourceRegistrationInput(
            source_type=SourceType.LECTURE_NOTE,
            title="Week 03 Chain Rule",
            content=original_content,
            mime_type="text/markdown",
            filename="week-03-chain-rule.md",
            tags=["week-03", "chain-rule"],
        ),
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        created_at=datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
    )

    stored_path = resolve_source_path(settings, source_record.origin_path)

    assert stored_path.read_text(encoding="utf-8") == original_content
    assert source_record.checksum == source_service.build_checksum(original_content)


def test_register_source_rejects_different_request_for_same_idempotency_key(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    registration = SourceRegistrationInput(
        source_type=SourceType.LECTURE_NOTE,
        title="Week 03 Chain Rule",
        content="# Chain Rule\nA compact note.",
        mime_type="text/markdown",
        filename="week-03-chain-rule.md",
        tags=["week-03", "chain-rule"],
    )
    register_source(
        settings,
        registration,
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        idempotency_key="idem-source-conflict",
    )

    with pytest.raises(SourceStateError, match="different request"):
        register_source(
            settings,
            registration.model_copy(update={"content": "# Chain Rule\nMaterially different."}),
            course_id="course-calculus-1",
            class_id="class-calculus-1-2026-spring-a",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-calculus-team",
            idempotency_key="idem-source-conflict",
        )


def test_register_source_rejects_cross_domain_replay_for_same_idempotency_key(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    registration = SourceRegistrationInput(
        source_type=SourceType.ANNOUNCEMENT,
        title="Homework Deadline Reminder",
        content="Homework 2 closes Friday at 23:59.",
        mime_type="text/plain",
        filename="announcement-homework-deadline.txt",
        tags=["homework", "deadline"],
    )
    register_source(
        settings,
        registration,
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        domain=RequestDomain.ACADEMIC,
        idempotency_key="idem-source-domain-conflict",
    )

    with pytest.raises(SourceStateError, match="different request"):
        register_source(
            settings,
            registration,
            course_id="course-calculus-1",
            class_id="class-calculus-1-2026-spring-a",
            actor_role=ActorRole.SYSTEM,
            actor_id="system-seed",
            domain=RequestDomain.OPERATIONS,
            idempotency_key="idem-source-domain-conflict",
        )


def test_register_source_uses_distinct_ids_and_paths_for_cross_domain_announcements(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    registration = SourceRegistrationInput(
        source_type=SourceType.ANNOUNCEMENT,
        title="Homework Deadline Reminder",
        content="Homework 2 closes Friday at 23:59.",
        mime_type="text/plain",
        filename="announcement-homework-deadline.txt",
        tags=["homework", "deadline"],
    )
    academic_source = register_source(
        settings,
        registration,
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        domain=RequestDomain.ACADEMIC,
        created_at=datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
    )
    operations_source = register_source(
        settings,
        registration,
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        domain=RequestDomain.OPERATIONS,
        created_at=datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
    )

    assert academic_source.source_id != operations_source.source_id
    assert academic_source.origin_path != operations_source.origin_path
    assert "/academic/" in academic_source.origin_path
    assert "/operations/" in operations_source.origin_path


def test_register_source_recovers_when_mark_applied_fails_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    registration = SourceRegistrationInput(
        source_type=SourceType.LECTURE_NOTE,
        title="Week 03 Chain Rule",
        content="# Chain Rule\nA compact note.",
        mime_type="text/markdown",
        filename="week-03-chain-rule.md",
        tags=["week-03", "chain-rule"],
    )
    original_mark_applied = source_service.mark_mutation_request_applied
    failed_once = {"value": False}

    def flaky_mark_applied(*args, **kwargs):  # noqa: ANN002, ANN003
        if not failed_once["value"]:
            failed_once["value"] = True
            raise sqlite3.OperationalError("forced mark_applied failure")
        return original_mark_applied(*args, **kwargs)

    monkeypatch.setattr(source_service, "mark_mutation_request_applied", flaky_mark_applied)

    with pytest.raises(sqlite3.OperationalError, match="forced mark_applied failure"):
        register_source(
            settings,
            registration,
            course_id="course-calculus-1",
            class_id="class-calculus-1-2026-spring-a",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-calculus-team",
            idempotency_key="idem-source-mark-applied",
        )

    mutation_request = get_mutation_request(
        settings,
        entity_type="source_registration",
        entity_id="source_store",
        action="source_registered",
        idempotency_key="idem-source-mark-applied",
    )
    assert mutation_request is not None
    assert mutation_request.status == "pending"

    recovered_source = register_source(
        settings,
        registration,
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        idempotency_key="idem-source-mark-applied",
    )
    mutation_request = get_mutation_request(
        settings,
        entity_type="source_registration",
        entity_id="source_store",
        action="source_registered",
        idempotency_key="idem-source-mark-applied",
    )

    assert recovered_source.source_id.startswith("src-lecture-note-")
    assert mutation_request is not None
    assert mutation_request.status == "applied"


def test_register_source_recovers_after_crash_before_audit_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    registration = SourceRegistrationInput(
        source_type=SourceType.LECTURE_NOTE,
        title="Week 03 Chain Rule",
        content="# Chain Rule\nA compact note.",
        mime_type="text/markdown",
        filename="week-03-chain-rule.md",
        tags=["week-03", "chain-rule"],
    )

    original_create_audit_event = source_service.create_audit_event

    def crash_before_audit(*args, **kwargs):  # noqa: ANN002, ANN003
        raise SystemExit("forced crash before audit commit")

    monkeypatch.setattr(source_service, "create_audit_event", crash_before_audit)

    with pytest.raises(SystemExit, match="forced crash before audit commit"):
        register_source(
            settings,
            registration,
            course_id="course-calculus-1",
            class_id="class-calculus-1-2026-spring-a",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-calculus-team",
            idempotency_key="idem-source-crash-recovery",
            created_at=datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
        )

    mutation_request = get_mutation_request(
        settings,
        entity_type="source_registration",
        entity_id="source_store",
        action="source_registered",
        idempotency_key="idem-source-crash-recovery",
    )
    manifest = load_manifest(settings)

    assert mutation_request is not None
    assert mutation_request.status == "pending"
    assert len(manifest.sources) == 1
    assert resolve_source_path(settings, manifest.sources[0].origin_path).exists()

    monkeypatch.setattr(source_service, "create_audit_event", original_create_audit_event)
    recovered_source = register_source(
        settings,
        registration,
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        idempotency_key="idem-source-crash-recovery",
        created_at=datetime(2026, 4, 8, 10, 31, tzinfo=UTC),
    )
    mutation_request = get_mutation_request(
        settings,
        entity_type="source_registration",
        entity_id="source_store",
        action="source_registered",
        idempotency_key="idem-source-crash-recovery",
    )

    assert recovered_source.source_id == manifest.sources[0].source_id
    assert mutation_request is not None
    assert mutation_request.status == "applied"


def test_register_source_recovers_after_crash_before_manifest_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    registration = SourceRegistrationInput(
        source_type=SourceType.LECTURE_NOTE,
        title="Week 03 Chain Rule",
        content="# Chain Rule\nA compact note.",
        mime_type="text/markdown",
        filename="week-03-chain-rule.md",
        tags=["week-03", "chain-rule"],
    )
    original_upsert_source_record = source_service.upsert_source_record

    def crash_before_manifest_update(*args, **kwargs):  # noqa: ANN002, ANN003
        raise SystemExit("forced crash before manifest update")

    monkeypatch.setattr(source_service, "upsert_source_record", crash_before_manifest_update)

    with pytest.raises(SystemExit, match="forced crash before manifest update"):
        register_source(
            settings,
            registration,
            course_id="course-calculus-1",
            class_id="class-calculus-1-2026-spring-a",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-calculus-team",
            idempotency_key="idem-source-manifest-recovery",
            created_at=datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
        )

    mutation_request = get_mutation_request(
        settings,
        entity_type="source_registration",
        entity_id="source_store",
        action="source_registered",
        idempotency_key="idem-source-manifest-recovery",
    )
    manifest = load_manifest(settings)

    assert mutation_request is not None
    assert mutation_request.status == "pending"
    assert manifest.sources == []
    raw_root = settings.data_root / "raw" / "lecture-note" / "class-calculus-1-2026-spring-a"
    stored_files = list(raw_root.glob("*.md"))
    assert len(stored_files) == 1

    monkeypatch.setattr(source_service, "upsert_source_record", original_upsert_source_record)
    recovered_source = register_source(
        settings,
        registration,
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        idempotency_key="idem-source-manifest-recovery",
        created_at=datetime(2026, 4, 8, 10, 31, tzinfo=UTC),
    )
    mutation_request = get_mutation_request(
        settings,
        entity_type="source_registration",
        entity_id="source_store",
        action="source_registered",
        idempotency_key="idem-source-manifest-recovery",
    )
    manifest = load_manifest(settings)

    assert recovered_source.source_id == manifest.sources[0].source_id
    assert mutation_request is not None
    assert mutation_request.status == "applied"


def test_register_source_rolls_back_when_audit_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    registration = SourceRegistrationInput(
        source_type=SourceType.LECTURE_NOTE,
        title="Week 03 Chain Rule",
        content="# Chain Rule\nA compact note.",
        mime_type="text/markdown",
        filename="week-03-chain-rule.md",
        tags=["week-03", "chain-rule"],
    )

    def fail_audit(*args, **kwargs):  # noqa: ANN002, ANN003
        raise sqlite3.IntegrityError("forced audit failure")

    monkeypatch.setattr(source_service, "create_audit_event", fail_audit)

    with pytest.raises(sqlite3.IntegrityError, match="forced audit failure"):
        register_source(
            settings,
            registration,
            course_id="course-calculus-1",
            class_id="class-calculus-1-2026-spring-a",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-calculus-team",
            created_at=datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
        )

    manifest = load_manifest(settings)
    assert manifest.sources == []
    raw_root = settings.data_root / "raw" / "lecture-note" / "class-calculus-1-2026-spring-a"
    assert not any(raw_root.glob("*"))


def test_operator_cannot_register_academic_source(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.post(
        "/api/v1/sources/register",
        headers=build_headers(
            role="operator",
            actor_id="ops-academic-office",
            idempotency_key="idem-operator-academic-forbidden",
        ),
        json={
            "source_type": "lecture_note",
            "title": "Week 03 Chain Rule",
            "content": "# Chain Rule",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_scope"


def test_instructor_can_register_academic_announcement(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.post(
        "/api/v1/sources/register",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            idempotency_key="idem-instructor-announcement",
        ),
        json={
            "source_type": "announcement",
            "title": "Homework Deadline Reminder",
            "content": "Homework 2 closes Friday at 23:59.",
            "mime_type": "text/plain",
            "filename": "announcement-homework-deadline.txt",
            "tags": ["homework", "deadline"],
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["domain"] == "academic"


def test_register_source_recovers_from_stale_manifest_lock(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    manifest_path = source_service.build_manifest_path(settings)
    lock_digest = hashlib.sha1(str(manifest_path).encode("utf-8")).hexdigest()[:12]
    lock_path = manifest_path.parent / f".lock-{lock_digest}"
    lock_path.write_text("stale-lock", encoding="utf-8")
    stale_timestamp = (
        datetime.now(UTC) - source_service.SOURCE_LOCK_STALE_AFTER - timedelta(seconds=1)
    ).timestamp()
    os.utime(lock_path, (stale_timestamp, stale_timestamp))

    source_record = register_source(
        settings,
        SourceRegistrationInput(
            source_type=SourceType.LECTURE_NOTE,
            title="Week 03 Chain Rule",
            content="# Chain Rule\nAcademic content.",
            mime_type="text/markdown",
            filename="week-03-chain-rule.md",
            tags=["week-03", "chain-rule"],
        ),
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        created_at=datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
    )

    assert source_record.source_id.startswith("src-lecture-note-")
    assert not lock_path.exists()


def test_register_source_endpoint_reports_storage_busy_for_active_manifest_lock(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    manifest_path = source_service.build_manifest_path(settings)
    lock_digest = hashlib.sha1(str(manifest_path).encode("utf-8")).hexdigest()[:12]
    lock_path = manifest_path.parent / f".lock-{lock_digest}"
    lock_path.write_text("active-lock", encoding="utf-8")

    response = client.post(
        "/api/v1/sources/register",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            idempotency_key="idem-active-lock",
        ),
        json={
            "source_type": "lecture_note",
            "title": "Week 03 Chain Rule",
            "content": "# Chain Rule",
            "mime_type": "text/markdown",
            "filename": "week-03-chain-rule.md",
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "storage_busy"


def test_system_registration_rejects_review_domain(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.post(
        "/api/v1/sources/register",
        headers={
            **build_headers(
                role="system",
                actor_id="system-seed",
                idempotency_key="idem-system-review-forbidden",
            ),
            "X-Knowloop-Domain": "review",
        },
        json={
            "source_type": "lecture_note",
            "title": "Week 03 Chain Rule",
            "content": "# Chain Rule",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_student_cannot_list_sources(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get(
        "/api/v1/sources",
        headers=build_headers(role="student", actor_id="stu-kim-minji"),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_role"


def test_validator_can_filter_sources_without_overriding_review_domain(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    register_source(
        settings,
        SourceRegistrationInput(
            source_type=SourceType.LECTURE_NOTE,
            title="Week 03 Chain Rule",
            content="# Chain Rule\nAcademic content.",
            mime_type="text/markdown",
            filename="week-03-chain-rule.md",
            tags=["week-03", "chain-rule"],
        ),
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        created_at=datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
    )

    response = client.get(
        "/api/v1/sources",
        headers=build_headers(role="validator", actor_id="val-course-admin"),
        params={"source_type": "lecture_note"},
    )

    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1
    assert response.json()["data"][0]["source_type"] == "lecture_note"


def test_system_review_domain_can_browse_cross_domain_sources(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    register_source(
        settings,
        SourceRegistrationInput(
            source_type=SourceType.LECTURE_NOTE,
            title="Week 03 Chain Rule",
            content="# Chain Rule\nAcademic content.",
            mime_type="text/markdown",
            filename="week-03-chain-rule.md",
            tags=["week-03", "chain-rule"],
        ),
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        created_at=datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
    )
    register_source(
        settings,
        SourceRegistrationInput(
            source_type=SourceType.OPERATIONS_NOTE,
            title="Refund Escalation Policy",
            content="Escalate refund questions to the academic office.",
            mime_type="text/plain",
            filename="refund-escalation.txt",
            tags=["refund"],
        ),
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        domain=RequestDomain.OPERATIONS,
        created_at=datetime(2026, 4, 8, 10, 35, tzinfo=UTC),
    )

    response = client.get(
        "/api/v1/sources",
        headers=build_headers(
            role="system",
            actor_id="system-seed",
            domain="review",
        ),
        params={"source_type": "lecture_note"},
    )

    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1
    assert response.json()["data"][0]["source_type"] == "lecture_note"


def test_system_source_endpoints_respect_explicit_domain_scope(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    academic_source = register_source(
        settings,
        SourceRegistrationInput(
            source_type=SourceType.LECTURE_NOTE,
            title="Week 03 Chain Rule",
            content="# Chain Rule\nAcademic content.",
            mime_type="text/markdown",
            filename="week-03-chain-rule.md",
            tags=["week-03", "chain-rule"],
        ),
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        created_at=datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
    )
    operations_source = register_source(
        settings,
        SourceRegistrationInput(
            source_type=SourceType.OPERATIONS_NOTE,
            title="Refund Escalation Policy",
            content="Escalate refund questions to the academic office.",
            mime_type="text/plain",
            filename="refund-escalation.txt",
            tags=["refund"],
        ),
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        domain=RequestDomain.OPERATIONS,
        created_at=datetime(2026, 4, 8, 10, 35, tzinfo=UTC),
    )

    list_response = client.get(
        "/api/v1/sources",
        headers=build_headers(
            role="system",
            actor_id="system-seed",
            domain="academic",
        ),
    )
    academic_detail_response = client.get(
        f"/api/v1/sources/{academic_source.source_id}",
        headers=build_headers(
            role="system",
            actor_id="system-seed",
            domain="academic",
        ),
    )
    operations_detail_response = client.get(
        f"/api/v1/sources/{operations_source.source_id}",
        headers=build_headers(
            role="system",
            actor_id="system-seed",
            domain="academic",
        ),
    )

    assert list_response.status_code == 200
    assert [item["domain"] for item in list_response.json()["data"]] == ["academic"]
    assert academic_detail_response.status_code == 200
    assert operations_detail_response.status_code == 403
    assert operations_detail_response.json()["error"]["code"] == "forbidden_scope"


def test_sources_list_and_detail_respect_role_scope(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    register_source(
        settings,
        SourceRegistrationInput(
            source_type=SourceType.LECTURE_NOTE,
            title="Week 03 Chain Rule",
            content="# Chain Rule\nAcademic content.",
            mime_type="text/markdown",
            filename="week-03-chain-rule.md",
            tags=["week-03", "chain-rule"],
        ),
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        created_at=datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
    )
    operations_source = register_source(
        settings,
        SourceRegistrationInput(
            source_type=SourceType.OPERATIONS_NOTE,
            title="Refund Escalation Policy",
            content="Escalate refund questions to the academic office.",
            mime_type="text/plain",
            filename="refund-escalation.txt",
            tags=["refund"],
        ),
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        domain=RequestDomain.OPERATIONS,
        created_at=datetime(2026, 4, 8, 10, 35, tzinfo=UTC),
    )

    list_response = client.get(
        "/api/v1/sources",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-list-sources",
        ),
        params={"q": "chain"},
    )
    detail_response = client.get(
        f"/api/v1/sources/{operations_source.source_id}",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-source-detail",
        ),
    )

    assert list_response.status_code == 200
    assert [item["source_type"] for item in list_response.json()["data"]] == ["lecture_note"]
    assert list_response.json()["meta"]["total"] == 1
    assert detail_response.status_code == 403
    assert detail_response.json()["error"]["code"] == "forbidden_scope"


def test_source_endpoints_require_request_context_headers(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get("/api/v1/sources")

    assert response.status_code == 422
    assert_server_owned_request_id(response, client_request_id=None)
    assert response.json()["error"]["code"] == "missing_context"


def test_register_source_endpoint_requires_idempotency_key(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.post(
        "/api/v1/sources/register",
        headers=build_headers(role="instructor", actor_id="ins-calculus-team"),
        json={
            "source_type": "lecture_note",
            "title": "Week 03 Chain Rule",
            "content": "# Chain Rule",
        },
    )

    assert response.status_code == 422
    assert_server_owned_request_id(response, client_request_id="req-test-source")
    assert response.json()["error"]["code"] == "validation_failed"
    assert response.json()["error"]["details"]["header"] == "Idempotency-Key"


def test_source_endpoints_reject_invalid_scope_headers(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get(
        "/api/v1/sources",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            class_id="..\\outside",
        ),
    )

    assert response.status_code == 422
    assert_server_owned_request_id(response, client_request_id="req-test-source")
    assert response.json()["error"]["code"] == "validation_failed"


def test_source_read_endpoints_reject_invalid_domain_override(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    source_record = register_source(
        settings,
        SourceRegistrationInput(
            source_type=SourceType.LECTURE_NOTE,
            title="Week 03 Chain Rule",
            content="# Chain Rule\nAcademic content.",
            mime_type="text/markdown",
            filename="week-03-chain-rule.md",
            tags=["week-03", "chain-rule"],
        ),
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        created_at=datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
    )

    list_response = client.get(
        "/api/v1/sources",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            domain="operations",
        ),
    )
    detail_response = client.get(
        f"/api/v1/sources/{source_record.source_id}",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            domain="operations",
        ),
    )

    assert list_response.status_code == 422
    assert_server_owned_request_id(list_response, client_request_id="req-test-source")
    assert list_response.json()["error"]["code"] == "validation_failed"
    assert detail_response.status_code == 422
    assert_server_owned_request_id(detail_response, client_request_id="req-test-source")
    assert detail_response.json()["error"]["code"] == "validation_failed"


def test_source_endpoints_reject_actor_id_role_mismatch(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.get(
        "/api/v1/sources",
        headers=build_headers(role="instructor", actor_id="stu-kim-minji"),
    )

    assert response.status_code == 422
    assert_server_owned_request_id(response, client_request_id="req-test-source")
    assert response.json()["error"]["code"] == "validation_failed"


def test_source_endpoints_wrap_body_validation_errors_in_contract_envelope(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.post(
        "/api/v1/sources/register",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            idempotency_key="idem-invalid-body",
        ),
        json={
            "source_type": "lecture-note",
            "title": "Week 03 Chain Rule",
            "content": "# Chain Rule",
        },
    )

    assert response.status_code == 422
    assert_server_owned_request_id(response, client_request_id="req-test-source")
    assert response.json()["error"]["code"] == "validation_failed"
    error_details = response.json()["error"]["details"]["errors"][0]
    assert "input" not in error_details
    assert error_details["loc"] == ["body", "source_type"]


def test_register_source_endpoint_wraps_manifest_failures_in_contract_envelope(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    manifest_path = source_service.build_manifest_path(settings)
    manifest_path.write_text("{invalid-json", encoding="utf-8")

    response = client.post(
        "/api/v1/sources/register",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            idempotency_key="idem-corrupt-manifest",
        ),
        json={
            "source_type": "lecture_note",
            "title": "Week 03 Chain Rule",
            "content": "# Chain Rule",
            "mime_type": "text/markdown",
            "filename": "week-03-chain-rule.md",
        },
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert_server_owned_request_id(response, client_request_id="req-test-source")


def test_register_source_endpoint_wraps_audit_failures_in_contract_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _settings = build_client(tmp_path)

    def fail_audit(*args, **kwargs):  # noqa: ANN002, ANN003
        raise sqlite3.OperationalError("forced audit failure")

    monkeypatch.setattr(source_service, "create_audit_event", fail_audit)

    response = client.post(
        "/api/v1/sources/register",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            idempotency_key="idem-audit-envelope",
        ),
        json={
            "source_type": "lecture_note",
            "title": "Week 03 Chain Rule",
            "content": "# Chain Rule",
            "mime_type": "text/markdown",
            "filename": "week-03-chain-rule.md",
        },
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert_server_owned_request_id(response, client_request_id="req-test-source")


def test_source_endpoints_reject_blank_titles_after_trimming(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.post(
        "/api/v1/sources/register",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            idempotency_key="idem-blank-title",
        ),
        json={
            "source_type": "lecture_note",
            "title": "   ",
            "content": "# Chain Rule",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_source_endpoints_reject_blank_content_after_trimming(tmp_path: Path) -> None:
    client, _settings = build_client(tmp_path)

    response = client.post(
        "/api/v1/sources/register",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            idempotency_key="idem-blank-content",
        ),
        json={
            "source_type": "lecture_note",
            "title": "Week 03 Chain Rule",
            "content": "   ",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_register_source_rejects_source_id_collision_with_different_extension(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    created_at = datetime(2026, 4, 8, 10, 30, tzinfo=UTC)
    first_registration = SourceRegistrationInput(
        source_type=SourceType.LECTURE_NOTE,
        title="Week 03 Chain Rule",
        content="# Chain Rule\nMarkdown version.",
        mime_type="text/markdown",
        filename="week-03-chain-rule.md",
        tags=["week-03", "chain-rule"],
    )
    second_registration = SourceRegistrationInput(
        source_type=SourceType.LECTURE_NOTE,
        title="Week 03 Chain Rule",
        content="Plain text version.",
        mime_type="text/plain",
        filename="week-03-chain-rule.txt",
        tags=["week-03", "chain-rule"],
    )

    stored_source = register_source(
        settings,
        first_registration,
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        created_at=created_at,
    )

    with pytest.raises(FileExistsError, match="source_id already exists"):
        register_source(
            settings,
            second_registration,
            course_id="course-calculus-1",
            class_id="class-calculus-1-2026-spring-a",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-calculus-team",
            created_at=created_at,
        )

    manifest = load_manifest(settings)
    assert [source.source_id for source in manifest.sources] == [stored_source.source_id]
    assert resolve_source_path(settings, stored_source.origin_path).suffix == ".md"


def test_register_source_uses_distinct_ids_for_non_ascii_titles(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    created_at = datetime(2026, 4, 8, 10, 30, tzinfo=UTC)
    first_source = register_source(
        settings,
        SourceRegistrationInput(
            source_type=SourceType.STUDENT_QUESTION,
            title="연쇄법칙 질문",
            content="합성함수 미분이 헷갈립니다.",
            mime_type="text/plain",
            filename="chain-rule-question-1.txt",
        ),
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        domain=RequestDomain.ACADEMIC,
        created_at=created_at,
    )
    second_source = register_source(
        settings,
        SourceRegistrationInput(
            source_type=SourceType.STUDENT_QUESTION,
            title="미분 규칙 질문",
            content="곱의 미분법이 헷갈립니다.",
            mime_type="text/plain",
            filename="product-rule-question.txt",
        ),
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        domain=RequestDomain.ACADEMIC,
        created_at=created_at,
    )

    assert first_source.source_id != second_source.source_id
    assert "-source-" in first_source.source_id
    assert "-source-" in second_source.source_id


def test_register_source_uses_distinct_ids_for_long_same_prefix_titles(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    created_at = datetime(2026, 4, 8, 10, 30, tzinfo=UTC)
    common_prefix = "week-03-chain-rule-" + ("verylong-" * 6)
    first_source = register_source(
        settings,
        SourceRegistrationInput(
            source_type=SourceType.LECTURE_NOTE,
            title=f"{common_prefix}example-a",
            content="# Chain Rule\nVariant A.",
            mime_type="text/markdown",
            filename="chain-rule-a.md",
        ),
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        created_at=created_at,
    )
    second_source = register_source(
        settings,
        SourceRegistrationInput(
            source_type=SourceType.LECTURE_NOTE,
            title=f"{common_prefix}example-b",
            content="# Chain Rule\nVariant B.",
            mime_type="text/markdown",
            filename="chain-rule-b.md",
        ),
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        created_at=created_at,
    )

    assert first_source.source_id != second_source.source_id
    assert resolve_source_path(settings, first_source.origin_path).exists()
    assert resolve_source_path(settings, second_source.origin_path).exists()


def test_register_source_endpoint_returns_conflict_for_non_idempotent_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _settings = build_client(tmp_path)
    fixed_source_id = "src-lecture-note-class-calculus-1-2026-spring-a-collision-20260408T103000Z"
    original_build_source_id = source_service.build_source_id
    calls = {"count": 0}

    def forced_collision(*args, **kwargs):  # noqa: ANN002, ANN003
        calls["count"] += 1
        if calls["count"] <= 2:
            return fixed_source_id
        return original_build_source_id(*args, **kwargs)

    monkeypatch.setattr(source_service, "build_source_id", forced_collision)

    first_response = client.post(
        "/api/v1/sources/register",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            idempotency_key="idem-endpoint-collision-a",
        ),
        json={
            "source_type": "lecture_note",
            "title": "Week 03 Chain Rule",
            "content": "# Chain Rule",
        },
    )
    second_response = client.post(
        "/api/v1/sources/register",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            idempotency_key="idem-endpoint-collision-b",
        ),
        json={
            "source_type": "lecture_note",
            "title": "Week 03 Chain Rule",
            "content": "# Chain Rule but different contents",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert_server_owned_request_id(first_response, client_request_id="req-test-source")
    assert_server_owned_request_id(second_response, client_request_id="req-test-source")
    assert second_response.json()["error"]["code"] == "duplicate_action"
