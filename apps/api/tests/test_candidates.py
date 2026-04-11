import hashlib
import json
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import knowloop_api.services.candidates as candidate_service
from knowloop_api.core.config import Settings
from knowloop_api.db.audit import (
    begin_mutation_request,
    build_audit_event_id,
    create_audit_event,
    get_mutation_request,
    list_audit_events,
    mark_mutation_request_applied,
    store_mutation_request_response_payload,
)
from knowloop_api.db.bootstrap import bootstrap_storage
from knowloop_api.services.candidates import (
    ActorRole,
    CandidateItem,
    CandidateKind,
    CandidateNotFoundError,
    CandidateStateError,
    CandidateStatus,
    create_candidate,
    drop_candidate,
    get_candidate,
    list_candidates,
    merge_candidate,
    promote_candidate,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "data" / "fixtures" / "candidates"


def build_settings(tmp_path: Path) -> Settings:
    # Keep the storage root short because Windows path length limits can exceed 260
    # characters once candidate IDs are embedded into nested class-scoped paths.
    digest = hashlib.sha1(str(tmp_path).encode("utf-8")).hexdigest()[:10]
    data_root = Path(tempfile.gettempdir()) / "kl" / digest
    shutil.rmtree(data_root, ignore_errors=True)
    return Settings(data_root=data_root)


def load_candidate_fixture(filename: str) -> CandidateItem:
    payload = json.loads((FIXTURE_ROOT / filename).read_text(encoding="utf-8"))
    return CandidateItem.model_validate(payload)


def test_create_candidate_persists_file_and_audit_event(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")

    created_candidate = create_candidate(
        settings,
        candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        request_id="req-create-candidate",
    )

    stored_candidate = get_candidate(settings, created_candidate.candidate_id)
    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=created_candidate.candidate_id,
    )

    assert stored_candidate == created_candidate
    assert audit_events[0].action == "candidate_created"
    assert audit_events[0].to_status == CandidateStatus.OPEN.value


def test_create_candidate_backfills_actor_role(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    candidate.actor_role = None

    created_candidate = create_candidate(
        settings,
        candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
    )

    assert created_candidate.actor_role is ActorRole.SYSTEM
    assert get_candidate(settings, created_candidate.candidate_id).actor_role is ActorRole.SYSTEM


def test_create_candidate_rejects_actor_role_drift(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    candidate.actor_role = ActorRole.OPERATOR

    with pytest.raises(CandidateStateError, match="actor_role must match"):
        create_candidate(
            settings,
            candidate,
            actor_role=ActorRole.SYSTEM,
            actor_id="system-seed",
        )


def test_create_candidate_repairs_missing_audit_for_existing_candidate(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    candidate_path = candidate_service.build_candidate_path(settings, candidate)
    candidate_service._write_candidate(candidate_path, candidate)

    repaired_candidate = create_candidate(
        settings,
        candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        request_id="req-repair-create",
    )
    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_created",
    )

    assert repaired_candidate == candidate
    assert len(audit_events) == 1
    assert audit_events[0].request_id == "req-repair-create"
    assert audit_events[0].notes == (
        "Recovered missing candidate_created audit from existing candidate file."
    )


def test_create_candidate_rejects_duplicate_candidate_id_across_paths(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    duplicate_candidate = candidate.model_copy(
        update={"class_id": "class-calculus-1-2026-spring-b"}
    )
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system-seed")

    with pytest.raises(FileExistsError, match="candidate already exists"):
        create_candidate(
            settings,
            duplicate_candidate,
            actor_role=ActorRole.SYSTEM,
            actor_id="system-seed",
        )


def test_create_candidate_is_idempotent_with_same_key_even_if_candidate_id_changes(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")

    first_result = create_candidate(
        settings,
        candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        idempotency_key="idem-create-1",
    )
    retried_candidate = candidate.model_copy(
        update={
            "candidate_id": "cand-faq-homework-deadline-retry",
            "created_at": candidate.created_at + timedelta(minutes=1),
        }
    )
    second_result = create_candidate(
        settings,
        retried_candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        idempotency_key="idem-create-1",
    )

    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        action="candidate_created",
        idempotency_key="idem-create-1",
    )

    assert second_result == first_result
    assert audit_events[0].entity_id == first_result.candidate_id
    assert len(audit_events) == 1
    with pytest.raises(CandidateNotFoundError):
        get_candidate(settings, retried_candidate.candidate_id)


def test_create_candidate_is_idempotent_when_updated_at_drifts_on_retry(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")

    first_result = create_candidate(
        settings,
        candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        idempotency_key="idem-create-updated-at",
    )
    retried_candidate = candidate.model_copy(
        update={
            "candidate_id": "cand-faq-homework-deadline-updated-at-retry",
            "created_at": candidate.created_at + timedelta(minutes=1),
            "updated_at": candidate.updated_at + timedelta(days=2),
        }
    )
    second_result = create_candidate(
        settings,
        retried_candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        idempotency_key="idem-create-updated-at",
    )

    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        action="candidate_created",
        idempotency_key="idem-create-updated-at",
    )

    assert second_result == first_result
    assert len(audit_events) == 1
    assert audit_events[0].entity_id == first_result.candidate_id
    with pytest.raises(CandidateNotFoundError):
        get_candidate(settings, retried_candidate.candidate_id)


def test_create_candidate_rejects_different_request_for_same_idempotency_key(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    create_candidate(
        settings,
        candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        idempotency_key="idem-create-shared",
    )

    with pytest.raises(CandidateStateError, match="different request"):
        create_candidate(
            settings,
            candidate.model_copy(
                update={
                    "candidate_id": "cand-faq-homework-deadline-retry-2",
                    "summary": "Materially different candidate payload.",
                }
            ),
            actor_role=ActorRole.SYSTEM,
            actor_id="system-seed",
            idempotency_key="idem-create-shared",
        )


def test_create_candidate_recovers_when_mark_applied_fails_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")

    original_mark_applied = candidate_service.mark_mutation_request_applied
    failed_once = {"value": False}

    def flaky_mark_applied(*args, **kwargs):  # noqa: ANN002, ANN003
        if not failed_once["value"]:
            failed_once["value"] = True
            raise sqlite3.OperationalError("forced mark_applied failure")
        return original_mark_applied(*args, **kwargs)

    monkeypatch.setattr(candidate_service, "mark_mutation_request_applied", flaky_mark_applied)

    with pytest.raises(sqlite3.OperationalError, match="forced mark_applied failure"):
        create_candidate(
            settings,
            candidate,
            actor_role=ActorRole.SYSTEM,
            actor_id="system-seed",
            idempotency_key="idem-create-mark-applied",
        )

    mutation_request = get_mutation_request(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-mark-applied",
    )
    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        action="candidate_created",
        idempotency_key="idem-create-mark-applied",
    )

    assert mutation_request is not None
    assert mutation_request.status == "pending"
    assert len(audit_events) == 1

    recovered_candidate = create_candidate(
        settings,
        candidate.model_copy(
            update={
                "candidate_id": "cand-faq-homework-deadline-recovered",
                "created_at": candidate.created_at + timedelta(minutes=2),
            }
        ),
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        idempotency_key="idem-create-mark-applied",
    )
    mutation_request = get_mutation_request(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-mark-applied",
    )

    assert recovered_candidate.candidate_id == candidate.candidate_id
    assert mutation_request is not None
    assert mutation_request.status == "applied"


def test_create_candidate_rejects_mismatched_replay_after_interrupted_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")

    original_mark_applied = candidate_service.mark_mutation_request_applied
    failed_once = {"value": False}

    def flaky_mark_applied(*args, **kwargs):  # noqa: ANN002, ANN003
        if not failed_once["value"]:
            failed_once["value"] = True
            raise sqlite3.OperationalError("forced mark_applied failure")
        return original_mark_applied(*args, **kwargs)

    monkeypatch.setattr(candidate_service, "mark_mutation_request_applied", flaky_mark_applied)

    with pytest.raises(sqlite3.OperationalError, match="forced mark_applied failure"):
        create_candidate(
            settings,
            candidate,
            actor_role=ActorRole.SYSTEM,
            actor_id="system-seed",
            idempotency_key="idem-create-mismatch",
        )

    stored_candidate = get_candidate(settings, candidate.candidate_id).model_copy(
        update={"summary": "Mutated after the interrupted write."}
    )
    candidate_path = candidate_service.find_candidate_path(settings, candidate.candidate_id)
    candidate_service._write_candidate(candidate_path, stored_candidate)

    with pytest.raises(
        CandidateStateError,
        match="stored created candidate does not match the idempotent request",
    ):
        create_candidate(
            settings,
            candidate.model_copy(
                update={
                    "candidate_id": "cand-faq-homework-deadline-mismatch-retry",
                    "created_at": candidate.created_at + timedelta(minutes=2),
                }
            ),
            actor_role=ActorRole.SYSTEM,
            actor_id="system-seed",
            idempotency_key="idem-create-mismatch",
        )


def test_create_candidate_recovers_when_file_exists_before_create_audit(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    request_fingerprint = candidate_service._build_candidate_create_request_fingerprint(
        candidate,
        actor_id="system-seed",
    )
    request_intent = candidate_service._build_candidate_create_request_intent(settings, candidate)
    begin_mutation_request(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-file-before-audit",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-seed",
        request_fingerprint=request_fingerprint,
        created_at=candidate.created_at,
    )
    store_mutation_request_response_payload(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-file-before-audit",
        updated_at=candidate.created_at,
        response_payload=request_intent,
    )
    candidate_path = candidate_service.build_candidate_path(settings, candidate)
    candidate_service._write_candidate(candidate_path, candidate)

    recovered_candidate = create_candidate(
        settings,
        candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        idempotency_key="idem-create-file-before-audit",
    )

    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        action="candidate_created",
        idempotency_key="idem-create-file-before-audit",
    )
    mutation_request = get_mutation_request(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-file-before-audit",
    )

    assert recovered_candidate == candidate
    assert len(audit_events) == 1
    assert audit_events[0].entity_id == candidate.candidate_id
    assert mutation_request is not None
    assert mutation_request.status == "applied"


def test_create_candidate_recovers_after_two_stage_retry_before_create_audit(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    request_fingerprint = candidate_service._build_candidate_create_request_fingerprint(
        candidate,
        actor_id="system-seed",
    )
    request_intent = candidate_service._build_candidate_create_request_intent(settings, candidate)
    begin_mutation_request(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-two-stage-before-audit",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-seed",
        request_fingerprint=request_fingerprint,
        created_at=candidate.created_at,
    )
    store_mutation_request_response_payload(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-two-stage-before-audit",
        updated_at=candidate.created_at,
        response_payload=request_intent,
    )

    second_attempt_path = candidate_service.build_candidate_path(settings, candidate)
    candidate_service._write_candidate(second_attempt_path, candidate)

    recovered_candidate = create_candidate(
        settings,
        candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        idempotency_key="idem-create-two-stage-before-audit",
    )

    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        action="candidate_created",
        idempotency_key="idem-create-two-stage-before-audit",
    )
    mutation_request = get_mutation_request(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-two-stage-before-audit",
    )

    assert recovered_candidate == candidate
    assert len(audit_events) == 1
    assert audit_events[0].entity_id == candidate.candidate_id
    assert mutation_request is not None
    assert mutation_request.status == "applied"


def test_create_candidate_reuses_pending_request_intent_before_any_artifact_exists(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    first_attempt_candidate = candidate.model_copy(
        update={
            "candidate_id": "cand-faq-homework-deadline-first-attempt",
            "created_at": candidate.created_at - timedelta(minutes=2),
            "updated_at": candidate.updated_at - timedelta(minutes=2),
        }
    )
    request_fingerprint = candidate_service._build_candidate_create_request_fingerprint(
        candidate,
        actor_id="system-seed",
    )
    begin_mutation_request(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-intent-mismatch",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-seed",
        request_fingerprint=request_fingerprint,
        created_at=first_attempt_candidate.created_at,
    )
    store_mutation_request_response_payload(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-intent-mismatch",
        updated_at=first_attempt_candidate.created_at,
        response_payload=candidate_service._build_candidate_create_request_intent(
            settings,
            first_attempt_candidate,
        ),
    )

    created_candidate = create_candidate(
        settings,
        candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        idempotency_key="idem-create-intent-mismatch",
    )
    mutation_request = get_mutation_request(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-intent-mismatch",
    )

    assert created_candidate.candidate_id == first_attempt_candidate.candidate_id
    assert created_candidate.created_at == first_attempt_candidate.created_at
    assert created_candidate.updated_at == first_attempt_candidate.created_at
    assert mutation_request is not None
    assert mutation_request.status == "applied"


def test_create_candidate_rejects_retry_when_pending_request_file_path_drifted(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    request_fingerprint = candidate_service._build_candidate_create_request_fingerprint(
        candidate,
        actor_id="system-seed",
    )
    request_intent = candidate_service._build_candidate_create_request_intent(settings, candidate)
    begin_mutation_request(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-path-drift",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-seed",
        request_fingerprint=request_fingerprint,
        created_at=candidate.created_at,
    )
    store_mutation_request_response_payload(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-path-drift",
        updated_at=candidate.created_at,
        response_payload=request_intent,
    )
    drifted_path = (
        settings.data_root
        / "candidate"
        / "faq"
        / "class-other"
        / f"{candidate.candidate_id}.json"
    )
    drifted_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_service._write_candidate(drifted_path, candidate)

    with pytest.raises(
        CandidateStateError,
        match="stored created candidate does not match the idempotent request",
    ):
        create_candidate(
            settings,
            candidate,
            actor_role=ActorRole.SYSTEM,
            actor_id="system-seed",
            idempotency_key="idem-create-path-drift",
        )


def test_create_candidate_does_not_recover_competing_pending_request(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    request_fingerprint = candidate_service._build_candidate_create_request_fingerprint(
        candidate,
        actor_id="system-seed",
    )
    begin_mutation_request(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-competing-a",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-seed",
        request_fingerprint=request_fingerprint,
        created_at=candidate.created_at,
    )
    stranded_candidate = candidate.model_copy(
        update={
            "candidate_id": "cand-faq-homework-deadline-stranded-a",
        }
    )
    stranded_path = candidate_service.build_candidate_path(settings, stranded_candidate)
    candidate_service._write_candidate(stranded_path, stranded_candidate)

    created_candidate = create_candidate(
        settings,
        candidate.model_copy(
            update={
                "candidate_id": "cand-faq-homework-deadline-competing-b",
                "created_at": candidate.created_at + timedelta(minutes=2),
                "updated_at": candidate.updated_at + timedelta(days=2),
            }
        ),
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        idempotency_key="idem-create-competing-b",
    )

    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        action="candidate_created",
        idempotency_key="idem-create-competing-b",
    )
    original_request = get_mutation_request(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-competing-a",
    )

    assert created_candidate.candidate_id == "cand-faq-homework-deadline-competing-b"
    assert audit_events[0].entity_id == created_candidate.candidate_id
    assert original_request is not None
    assert original_request.status == "pending"
    assert get_candidate(settings, stranded_candidate.candidate_id).candidate_id == (
        stranded_candidate.candidate_id
    )


def test_create_candidate_rejects_existing_candidate_claim_when_other_pending_request_matches(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    request_fingerprint = candidate_service._build_candidate_create_request_fingerprint(
        candidate,
        actor_id="system-seed",
    )
    begin_mutation_request(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-existing-pending-a",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-seed",
        request_fingerprint=request_fingerprint,
        created_at=candidate.created_at,
    )
    candidate_path = candidate_service.build_candidate_path(settings, candidate)
    candidate_service._write_candidate(candidate_path, candidate)

    with pytest.raises(
        CandidateStateError,
        match="candidate already exists under another pending request",
    ):
        create_candidate(
            settings,
            candidate,
            actor_role=ActorRole.SYSTEM,
            actor_id="system-seed",
            idempotency_key="idem-create-existing-pending-b",
        )


def test_create_candidate_rejects_existing_audited_candidate_for_new_idempotency_key(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")

    create_candidate(
        settings,
        candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        idempotency_key="idem-create-lineage-a",
    )

    with pytest.raises(
        CandidateStateError,
        match="stored created candidate does not match the idempotent request",
    ):
        create_candidate(
            settings,
            candidate,
            actor_role=ActorRole.SYSTEM,
            actor_id="system-seed",
            idempotency_key="idem-create-lineage-b",
        )


def test_create_candidate_does_not_recover_older_audited_logical_twin(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    original_candidate = create_candidate(
        settings,
        candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        request_id="req-original-audited-twin",
    )
    retried_candidate = candidate.model_copy(
        update={
            "candidate_id": "cand-faq-homework-deadline-new-logical-run",
            "created_at": candidate.created_at + timedelta(minutes=5),
            "updated_at": candidate.updated_at + timedelta(days=1),
        }
    )
    request_fingerprint = candidate_service._build_candidate_create_request_fingerprint(
        retried_candidate,
        actor_id="system-seed",
    )
    begin_mutation_request(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-ignore-audited-twin",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-seed",
        request_fingerprint=request_fingerprint,
        created_at=candidate.created_at,
    )

    created_candidate = create_candidate(
        settings,
        retried_candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        idempotency_key="idem-create-ignore-audited-twin",
    )

    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        action="candidate_created",
        idempotency_key="idem-create-ignore-audited-twin",
    )
    mutation_request = get_mutation_request(
        settings,
        entity_type="candidate_registration",
        entity_id="candidate_store",
        action="candidate_created",
        idempotency_key="idem-create-ignore-audited-twin",
    )

    assert created_candidate.candidate_id == retried_candidate.candidate_id
    assert created_candidate.candidate_id != original_candidate.candidate_id
    assert len(audit_events) == 1
    assert audit_events[0].entity_id == retried_candidate.candidate_id
    assert mutation_request is not None
    assert mutation_request.status == "applied"


def test_create_candidate_rejects_ambiguous_audit_replay(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    create_candidate(
        settings,
        candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system-seed",
        idempotency_key="idem-create-ambiguous",
    )
    create_audit_event(
        settings,
        entity_type="candidate",
        entity_id="cand-faq-corrupt-replay",
        action="candidate_created",
        actor_role=ActorRole.SYSTEM.value,
        actor_id="system-seed",
        to_status=CandidateStatus.OPEN.value,
        idempotency_key="idem-create-ambiguous",
        created_at=candidate.created_at + timedelta(seconds=1),
    )

    with pytest.raises(CandidateStateError, match="ambiguous"):
        create_candidate(
            settings,
            candidate.model_copy(
                update={
                    "candidate_id": "cand-faq-corrupt-retry",
                    "created_at": candidate.created_at + timedelta(minutes=1),
                }
            ),
            actor_role=ActorRole.SYSTEM,
            actor_id="system-seed",
            idempotency_key="idem-create-ambiguous",
        )


def test_promote_candidate_updates_approval_fields_and_audit(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system-seed")

    promoted_candidate = promote_candidate(
        settings,
        candidate.candidate_id,
        approved_by="ins-calculus-team",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        related_page_id="page-faq-homework-submission",
        request_id="req-promote-candidate",
    )

    reloaded_candidate = get_candidate(settings, candidate.candidate_id)
    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
    )

    assert promoted_candidate.status is CandidateStatus.PROMOTED
    assert promoted_candidate.approved_by == "ins-calculus-team"
    assert promoted_candidate.related_page_id == "page-faq-homework-submission"
    assert reloaded_candidate == promoted_candidate
    assert audit_events[0].from_status == CandidateStatus.OPEN.value
    assert audit_events[0].to_status == CandidateStatus.PROMOTED.value


def test_promote_candidate_is_idempotent_with_same_key(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system-seed")

    first_result = promote_candidate(
        settings,
        candidate.candidate_id,
        approved_by="ins-calculus-team",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        related_page_id="page-faq-homework-submission",
        request_id="req-promote-candidate",
        idempotency_key="idem-promote-1",
    )
    second_result = promote_candidate(
        settings,
        candidate.candidate_id,
        approved_by="ins-calculus-team",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        related_page_id="page-faq-homework-submission",
        request_id="req-promote-candidate-retry",
        idempotency_key="idem-promote-1",
    )

    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
    )

    assert second_result == first_result
    assert len(audit_events) == 1
    assert audit_events[0].idempotency_key == "idem-promote-1"


def test_promote_candidate_rejects_different_request_for_same_idempotency_key(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system-seed")

    promote_candidate(
        settings,
        candidate.candidate_id,
        approved_by="ins-calculus-team",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        related_page_id="page-faq-homework-submission",
        idempotency_key="idem-promote-shared",
    )

    with pytest.raises(CandidateStateError, match="different request"):
        promote_candidate(
            settings,
            candidate.candidate_id,
            approved_by="ins-calculus-team",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-calculus-team",
            related_page_id="page-faq-other-policy",
            idempotency_key="idem-promote-shared",
        )


def test_promote_candidate_rejects_timestamp_drift_for_same_idempotency_key(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system-seed")

    promote_candidate(
        settings,
        candidate.candidate_id,
        approved_by="ins-calculus-team",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        related_page_id="page-faq-homework-submission",
        idempotency_key="idem-promote-time",
        approved_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(CandidateStateError, match="different request"):
        promote_candidate(
            settings,
            candidate.candidate_id,
            approved_by="ins-calculus-team",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-calculus-team",
            related_page_id="page-faq-homework-submission",
            idempotency_key="idem-promote-time",
            approved_at=datetime(2026, 4, 8, 12, 5, tzinfo=UTC),
        )


def test_promote_candidate_recovers_duplicate_in_flight_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system-seed")

    original_apply_transaction = candidate_service._apply_candidate_transaction
    failed_once = {"value": False}

    def simulate_racing_duplicate(*args, **kwargs):  # noqa: ANN002, ANN003
        if not failed_once["value"]:
            failed_once["value"] = True
            changes = args[0]
            for path, changed_candidate in changes.items():
                candidate_service._write_candidate(path, changed_candidate)
            raise CandidateStateError("candidate changed during transition")
        return original_apply_transaction(*args, **kwargs)

    monkeypatch.setattr(
        candidate_service,
        "_apply_candidate_transaction",
        simulate_racing_duplicate,
    )

    promoted_candidate = promote_candidate(
        settings,
        candidate.candidate_id,
        approved_by="ins-calculus-team",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        related_page_id="page-faq-homework-submission",
        idempotency_key="idem-promote-racing",
    )
    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
        idempotency_key="idem-promote-racing",
    )

    assert promoted_candidate.status is CandidateStatus.PROMOTED
    assert len(audit_events) == 1


def test_promote_candidate_recovers_pending_idempotent_transition(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system-seed")

    promoted_candidate = candidate.model_copy(
        update={
            "status": CandidateStatus.PROMOTED,
            "approved_by": "ins-calculus-team",
            "approved_at": datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
            "related_page_id": "page-faq-homework-submission",
        }
    )
    candidate_path = candidate_service.find_candidate_path(settings, candidate.candidate_id)
    candidate_service._write_candidate(candidate_path, promoted_candidate)
    begin_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
        idempotency_key="idem-promote-recover",
        actor_role=ActorRole.INSTRUCTOR.value,
        actor_id="ins-calculus-team",
        request_fingerprint=candidate_service._build_request_fingerprint(
            candidate_id=candidate.candidate_id,
            action="candidate_promoted",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-calculus-team",
            approved_by="ins-calculus-team",
            related_page_id="page-faq-homework-submission",
            requested_approved_at=None,
            notes=None,
        ),
        created_at=promoted_candidate.approved_at,
    )

    recovered_candidate = promote_candidate(
        settings,
        candidate.candidate_id,
        approved_by="ins-calculus-team",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        related_page_id="page-faq-homework-submission",
        idempotency_key="idem-promote-recover",
    )

    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
        idempotency_key="idem-promote-recover",
    )

    assert recovered_candidate.status is CandidateStatus.PROMOTED
    assert len(audit_events) == 1


def test_promote_candidate_does_not_claim_later_matching_transition(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system-seed")

    promoted_candidate = candidate.model_copy(
        update={
            "status": CandidateStatus.PROMOTED,
            "approved_by": "ins-calculus-team",
            "approved_at": datetime(2026, 4, 8, 12, 5, tzinfo=UTC),
            "related_page_id": "page-faq-homework-submission",
        }
    )
    candidate_path = candidate_service.find_candidate_path(settings, candidate.candidate_id)
    candidate_service._write_candidate(candidate_path, promoted_candidate)
    begin_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
        idempotency_key="idem-promote-old-pending",
        actor_role=ActorRole.INSTRUCTOR.value,
        actor_id="ins-calculus-team",
        request_fingerprint=candidate_service._build_request_fingerprint(
            candidate_id=candidate.candidate_id,
            action="candidate_promoted",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-calculus-team",
            approved_by="ins-calculus-team",
            related_page_id="page-faq-homework-submission",
            requested_approved_at=None,
            notes=None,
        ),
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(CandidateStateError):
        promote_candidate(
            settings,
            candidate.candidate_id,
            approved_by="ins-calculus-team",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-calculus-team",
            related_page_id="page-faq-homework-submission",
            idempotency_key="idem-promote-old-pending",
        )


def test_promote_candidate_recovers_when_mark_applied_fails_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system-seed")

    original_mark_applied = candidate_service.mark_mutation_request_applied
    failed_once = {"value": False}

    def flaky_mark_applied(*args, **kwargs):  # noqa: ANN002, ANN003
        if not failed_once["value"]:
            failed_once["value"] = True
            raise sqlite3.OperationalError("forced mark_applied failure")
        return original_mark_applied(*args, **kwargs)

    monkeypatch.setattr(candidate_service, "mark_mutation_request_applied", flaky_mark_applied)

    with pytest.raises(sqlite3.OperationalError, match="forced mark_applied failure"):
        promote_candidate(
            settings,
            candidate.candidate_id,
            approved_by="ins-calculus-team",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-calculus-team",
            related_page_id="page-faq-homework-submission",
            idempotency_key="idem-promote-mark-applied",
        )

    current_candidate = get_candidate(settings, candidate.candidate_id)
    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
        idempotency_key="idem-promote-mark-applied",
    )
    mutation_request = get_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
        idempotency_key="idem-promote-mark-applied",
    )

    assert current_candidate.status is CandidateStatus.PROMOTED
    assert len(audit_events) == 1
    assert mutation_request is not None
    assert mutation_request.status == "pending"

    recovered_candidate = promote_candidate(
        settings,
        candidate.candidate_id,
        approved_by="ins-calculus-team",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        related_page_id="page-faq-homework-submission",
        idempotency_key="idem-promote-mark-applied",
    )
    mutation_request = get_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
        idempotency_key="idem-promote-mark-applied",
    )

    assert recovered_candidate.status is CandidateStatus.PROMOTED
    assert mutation_request is not None
    assert mutation_request.status == "applied"


def test_promote_candidate_rejects_mismatched_applied_replay(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system-seed")

    mutation_request = begin_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
        idempotency_key="idem-promote-applied-mismatch",
        actor_role=ActorRole.INSTRUCTOR.value,
        actor_id="ins-calculus-team",
        request_fingerprint=candidate_service._build_request_fingerprint(
            candidate_id=candidate.candidate_id,
            action="candidate_promoted",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-calculus-team",
            approved_by="ins-calculus-team",
            related_page_id="page-faq-homework-submission",
            requested_approved_at=None,
            notes=None,
        ),
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
    )
    mark_mutation_request_applied(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_promoted",
        idempotency_key="idem-promote-applied-mismatch",
        updated_at=mutation_request.created_at,
    )

    with pytest.raises(CandidateStateError, match="stored promoted candidate does not match"):
        promote_candidate(
            settings,
            candidate.candidate_id,
            approved_by="ins-calculus-team",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-calculus-team",
            related_page_id="page-faq-homework-submission",
            idempotency_key="idem-promote-applied-mismatch",
        )


def test_mark_mutation_request_applied_keeps_updated_at_monotonic(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    record = begin_mutation_request(
        settings,
        entity_type="candidate",
        entity_id="cand-monotonic",
        action="candidate_promoted",
        idempotency_key="idem-monotonic",
        actor_role=ActorRole.INSTRUCTOR.value,
        actor_id="ins-calculus-team",
        request_fingerprint="fingerprint",
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
    )

    first_update = mark_mutation_request_applied(
        settings,
        entity_type="candidate",
        entity_id="cand-monotonic",
        action="candidate_promoted",
        idempotency_key="idem-monotonic",
        updated_at=record.created_at + timedelta(minutes=5),
    )
    second_update = mark_mutation_request_applied(
        settings,
        entity_type="candidate",
        entity_id="cand-monotonic",
        action="candidate_promoted",
        idempotency_key="idem-monotonic",
        updated_at=record.created_at,
    )

    assert first_update.updated_at == second_update.updated_at


def test_promote_candidate_requires_approver_identity_match(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system-seed")

    with pytest.raises(CandidateStateError, match="approved_by must match actor_id"):
        promote_candidate(
            settings,
            candidate.candidate_id,
            approved_by="ins-calculus-team",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-other-reviewer",
            related_page_id="page-faq-homework-submission",
        )


def test_promote_candidate_requires_actor_id(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system-seed")

    with pytest.raises(CandidateStateError, match="actor_id is required"):
        promote_candidate(
            settings,
            candidate.candidate_id,
            approved_by="ins-calculus-team",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id=None,
            related_page_id="page-faq-homework-submission",
        )


def test_promote_candidate_requires_target_page_id(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-unresolved-integral.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    with pytest.raises(CandidateStateError, match="target wiki page"):
        promote_candidate(
            settings,
            candidate.candidate_id,
            approved_by="ins-calculus-team",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-calculus-team",
        )


def test_unresolved_candidates_cannot_be_promoted_directly(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-unresolved-integral.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    with pytest.raises(CandidateStateError, match="cannot be promoted directly"):
        promote_candidate(
            settings,
            candidate.candidate_id,
            approved_by="ins-calculus-team",
            actor_role=ActorRole.INSTRUCTOR,
            actor_id="ins-calculus-team",
            related_page_id="page-faq-homework-submission",
        )


def test_merge_candidate_marks_source_candidate_and_enriches_target(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    canonical_candidate = load_candidate_fixture("open-misconception-chain-rule.json")
    duplicate_candidate = load_candidate_fixture("open-misconception-chain-rule-duplicate.json")
    create_candidate(settings, canonical_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")
    create_candidate(settings, duplicate_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    merged_candidate = merge_candidate(
        settings,
        duplicate_candidate.candidate_id,
        target_candidate_id=canonical_candidate.candidate_id,
        actor_role=ActorRole.VALIDATOR,
        actor_id="val-course-admin",
        request_id="req-merge-candidate",
    )

    refreshed_target = get_candidate(settings, canonical_candidate.candidate_id)
    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=duplicate_candidate.candidate_id,
        action="candidate_merged",
    )

    assert merged_candidate.status is CandidateStatus.MERGED
    assert merged_candidate.merged_into == canonical_candidate.candidate_id
    assert "duplicate" in refreshed_target.tags
    assert duplicate_candidate.session_refs[0] in refreshed_target.session_refs
    assert audit_events[0].to_status == CandidateStatus.MERGED.value


def test_merge_candidate_is_idempotent_with_same_key(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    canonical_candidate = load_candidate_fixture("open-misconception-chain-rule.json")
    duplicate_candidate = load_candidate_fixture("open-misconception-chain-rule-duplicate.json")
    create_candidate(settings, canonical_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")
    create_candidate(settings, duplicate_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    first_result = merge_candidate(
        settings,
        duplicate_candidate.candidate_id,
        target_candidate_id=canonical_candidate.candidate_id,
        actor_role=ActorRole.VALIDATOR,
        actor_id="val-course-admin",
        idempotency_key="idem-merge-1",
    )
    second_result = merge_candidate(
        settings,
        duplicate_candidate.candidate_id,
        target_candidate_id=canonical_candidate.candidate_id,
        actor_role=ActorRole.VALIDATOR,
        actor_id="val-course-admin",
        idempotency_key="idem-merge-1",
    )

    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=duplicate_candidate.candidate_id,
        action="candidate_merged",
    )

    assert second_result == first_result
    assert len(audit_events) == 1
    assert audit_events[0].idempotency_key == "idem-merge-1"


def test_merge_candidate_recovers_pending_idempotent_transition(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    canonical_candidate = load_candidate_fixture("open-misconception-chain-rule.json")
    duplicate_candidate = load_candidate_fixture("open-misconception-chain-rule-duplicate.json")
    create_candidate(settings, canonical_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")
    create_candidate(settings, duplicate_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    transition_at = datetime(2026, 4, 8, 12, 40, tzinfo=UTC)
    merged_candidate = duplicate_candidate.model_copy(
        update={
            "status": CandidateStatus.MERGED,
            "merged_into": canonical_candidate.candidate_id,
            "approved_by": "val-course-admin",
            "approved_at": transition_at,
        }
    )
    updated_target = canonical_candidate.model_copy(
        update={
            "tags": candidate_service._merge_unique_strings(
                canonical_candidate.tags,
                duplicate_candidate.tags,
            ),
            "session_refs": candidate_service._merge_unique_strings(
                canonical_candidate.session_refs,
                duplicate_candidate.session_refs,
            ),
            "source_refs": candidate_service._merge_source_refs(
                canonical_candidate.source_refs,
                duplicate_candidate.source_refs,
            ),
        }
    )
    candidate_service._write_candidate(
        candidate_service.find_candidate_path(settings, duplicate_candidate.candidate_id),
        merged_candidate,
    )
    candidate_service._write_candidate(
        candidate_service.find_candidate_path(settings, canonical_candidate.candidate_id),
        updated_target,
    )
    begin_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=duplicate_candidate.candidate_id,
        action="candidate_merged",
        idempotency_key="idem-merge-recover",
        actor_role=ActorRole.VALIDATOR.value,
        actor_id="val-course-admin",
        request_fingerprint=candidate_service._build_request_fingerprint(
            candidate_id=duplicate_candidate.candidate_id,
            action="candidate_merged",
            actor_role=ActorRole.VALIDATOR,
            actor_id="val-course-admin",
            target_candidate_id=canonical_candidate.candidate_id,
            target_identity=candidate_service._build_merge_target_identity(canonical_candidate),
            requested_merged_at=None,
            notes=None,
        ),
        created_at=transition_at,
    )

    recovered_candidate = merge_candidate(
        settings,
        duplicate_candidate.candidate_id,
        target_candidate_id=canonical_candidate.candidate_id,
        actor_role=ActorRole.VALIDATOR,
        actor_id="val-course-admin",
        idempotency_key="idem-merge-recover",
    )
    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=duplicate_candidate.candidate_id,
        action="candidate_merged",
        idempotency_key="idem-merge-recover",
    )

    assert recovered_candidate.status is CandidateStatus.MERGED
    assert len(audit_events) == 1


def test_merge_candidate_rejects_pending_replay_when_target_metadata_drifts(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    canonical_candidate = load_candidate_fixture("open-misconception-chain-rule.json")
    duplicate_candidate = load_candidate_fixture("open-misconception-chain-rule-duplicate.json")
    create_candidate(settings, canonical_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")
    create_candidate(settings, duplicate_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    transition_at = datetime(2026, 4, 8, 12, 41, tzinfo=UTC)
    merged_candidate = duplicate_candidate.model_copy(
        update={
            "status": CandidateStatus.MERGED,
            "merged_into": canonical_candidate.candidate_id,
            "approved_by": "val-course-admin",
            "approved_at": transition_at,
        }
    )
    drifted_target = canonical_candidate.model_copy(
        update={
            "summary": "Drifted target summary after interrupted merge.",
            "tags": candidate_service._merge_unique_strings(
                canonical_candidate.tags,
                duplicate_candidate.tags,
            ),
            "session_refs": candidate_service._merge_unique_strings(
                canonical_candidate.session_refs,
                duplicate_candidate.session_refs,
            ),
            "source_refs": candidate_service._merge_source_refs(
                canonical_candidate.source_refs,
                duplicate_candidate.source_refs,
            ),
        }
    )
    candidate_service._write_candidate(
        candidate_service.find_candidate_path(settings, duplicate_candidate.candidate_id),
        merged_candidate,
    )
    candidate_service._write_candidate(
        candidate_service.find_candidate_path(settings, canonical_candidate.candidate_id),
        drifted_target,
    )
    begin_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=duplicate_candidate.candidate_id,
        action="candidate_merged",
        idempotency_key="idem-merge-drifted-target",
        actor_role=ActorRole.VALIDATOR.value,
        actor_id="val-course-admin",
        request_fingerprint=candidate_service._build_request_fingerprint(
            candidate_id=duplicate_candidate.candidate_id,
            action="candidate_merged",
            actor_role=ActorRole.VALIDATOR,
            actor_id="val-course-admin",
            target_candidate_id=canonical_candidate.candidate_id,
            target_identity=candidate_service._build_merge_target_identity(canonical_candidate),
            requested_merged_at=None,
            notes=None,
        ),
        created_at=transition_at,
    )

    with pytest.raises(CandidateStateError, match="different request"):
        merge_candidate(
            settings,
            duplicate_candidate.candidate_id,
            target_candidate_id=canonical_candidate.candidate_id,
            actor_role=ActorRole.VALIDATOR,
            actor_id="val-course-admin",
            idempotency_key="idem-merge-drifted-target",
        )

    refreshed_source = get_candidate(settings, duplicate_candidate.candidate_id)
    refreshed_target = get_candidate(settings, canonical_candidate.candidate_id)
    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=duplicate_candidate.candidate_id,
        action="candidate_merged",
        idempotency_key="idem-merge-drifted-target",
    )

    assert refreshed_source.status is CandidateStatus.MERGED
    assert refreshed_source.merged_into == canonical_candidate.candidate_id
    assert refreshed_target.summary == drifted_target.summary
    assert audit_events == []


def test_merge_candidate_rejects_timestamp_drift_for_same_idempotency_key(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    canonical_candidate = load_candidate_fixture("open-misconception-chain-rule.json")
    duplicate_candidate = load_candidate_fixture("open-misconception-chain-rule-duplicate.json")
    create_candidate(settings, canonical_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")
    create_candidate(settings, duplicate_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    merge_candidate(
        settings,
        duplicate_candidate.candidate_id,
        target_candidate_id=canonical_candidate.candidate_id,
        actor_role=ActorRole.VALIDATOR,
        actor_id="val-course-admin",
        idempotency_key="idem-merge-time",
        merged_at=datetime(2026, 4, 8, 12, 10, tzinfo=UTC),
    )

    with pytest.raises(CandidateStateError, match="different request"):
        merge_candidate(
            settings,
            duplicate_candidate.candidate_id,
            target_candidate_id=canonical_candidate.candidate_id,
            actor_role=ActorRole.VALIDATOR,
            actor_id="val-course-admin",
            idempotency_key="idem-merge-time",
            merged_at=datetime(2026, 4, 8, 12, 15, tzinfo=UTC),
        )


def test_merge_candidate_rejects_cross_scope_target(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    source_candidate = load_candidate_fixture("open-misconception-chain-rule-duplicate.json")
    target_candidate = load_candidate_fixture("open-operations-refund.json")
    create_candidate(settings, source_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")
    create_candidate(settings, target_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    with pytest.raises(CandidateStateError, match="same candidate kind"):
        merge_candidate(
            settings,
            source_candidate.candidate_id,
            target_candidate_id=target_candidate.candidate_id,
            actor_role=ActorRole.VALIDATOR,
            actor_id="val-course-admin",
        )


def test_merge_candidate_recovers_when_mark_applied_fails_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    canonical_candidate = load_candidate_fixture("open-misconception-chain-rule.json")
    duplicate_candidate = load_candidate_fixture("open-misconception-chain-rule-duplicate.json")
    create_candidate(settings, canonical_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")
    create_candidate(settings, duplicate_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    original_mark_applied = candidate_service.mark_mutation_request_applied
    failed_once = {"value": False}

    def flaky_mark_applied(*args, **kwargs):  # noqa: ANN002, ANN003
        if not failed_once["value"]:
            failed_once["value"] = True
            raise sqlite3.OperationalError("forced mark_applied failure")
        return original_mark_applied(*args, **kwargs)

    monkeypatch.setattr(candidate_service, "mark_mutation_request_applied", flaky_mark_applied)

    with pytest.raises(sqlite3.OperationalError, match="forced mark_applied failure"):
        merge_candidate(
            settings,
            duplicate_candidate.candidate_id,
            target_candidate_id=canonical_candidate.candidate_id,
            actor_role=ActorRole.VALIDATOR,
            actor_id="val-course-admin",
            idempotency_key="idem-merge-mark-applied",
        )

    mutation_request = get_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=duplicate_candidate.candidate_id,
        action="candidate_merged",
        idempotency_key="idem-merge-mark-applied",
    )
    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=duplicate_candidate.candidate_id,
        action="candidate_merged",
        idempotency_key="idem-merge-mark-applied",
    )

    assert mutation_request is not None
    assert mutation_request.status == "pending"
    assert len(audit_events) == 1

    recovered_candidate = merge_candidate(
        settings,
        duplicate_candidate.candidate_id,
        target_candidate_id=canonical_candidate.candidate_id,
        actor_role=ActorRole.VALIDATOR,
        actor_id="val-course-admin",
        idempotency_key="idem-merge-mark-applied",
    )
    mutation_request = get_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=duplicate_candidate.candidate_id,
        action="candidate_merged",
        idempotency_key="idem-merge-mark-applied",
    )

    assert recovered_candidate.status is CandidateStatus.MERGED
    assert mutation_request is not None
    assert mutation_request.status == "applied"


def test_merge_candidate_rejects_mismatched_applied_replay(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    canonical_candidate = load_candidate_fixture("open-misconception-chain-rule.json")
    duplicate_candidate = load_candidate_fixture("open-misconception-chain-rule-duplicate.json")
    create_candidate(settings, canonical_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")
    create_candidate(settings, duplicate_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    mutation_request = begin_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=duplicate_candidate.candidate_id,
        action="candidate_merged",
        idempotency_key="idem-merge-applied-mismatch",
        actor_role=ActorRole.VALIDATOR.value,
        actor_id="val-course-admin",
        request_fingerprint=candidate_service._build_request_fingerprint(
            candidate_id=duplicate_candidate.candidate_id,
            action="candidate_merged",
            actor_role=ActorRole.VALIDATOR,
            actor_id="val-course-admin",
            target_candidate_id=canonical_candidate.candidate_id,
            target_identity=candidate_service._build_merge_target_identity(canonical_candidate),
            requested_merged_at=None,
            notes=None,
        ),
        created_at=datetime(2026, 4, 8, 12, 45, tzinfo=UTC),
    )
    mark_mutation_request_applied(
        settings,
        entity_type="candidate",
        entity_id=duplicate_candidate.candidate_id,
        action="candidate_merged",
        idempotency_key="idem-merge-applied-mismatch",
        updated_at=mutation_request.created_at,
    )

    with pytest.raises(CandidateStateError, match="stored merged candidate does not match"):
        merge_candidate(
            settings,
            duplicate_candidate.candidate_id,
            target_candidate_id=canonical_candidate.candidate_id,
            actor_role=ActorRole.VALIDATOR,
            actor_id="val-course-admin",
            idempotency_key="idem-merge-applied-mismatch",
        )


def test_drop_candidate_marks_candidate_dropped_and_writes_audit(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-unresolved-integral.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    dropped_candidate = drop_candidate(
        settings,
        candidate.candidate_id,
        actor_role=ActorRole.VALIDATOR,
        actor_id="val-course-admin",
        request_id="req-drop-candidate",
        reason="insufficient_shared_value",
        notes="Not enough shared value for promotion yet.",
    )

    reloaded_candidate = get_candidate(settings, candidate.candidate_id)
    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_dropped",
    )

    assert dropped_candidate.status is CandidateStatus.DROPPED
    assert reloaded_candidate.status is CandidateStatus.DROPPED
    assert audit_events[0].notes == "Not enough shared value for promotion yet."
    assert audit_events[0].details == {"reason": "insufficient_shared_value"}


def test_drop_candidate_is_idempotent_with_same_key(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-unresolved-integral.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    first_result = drop_candidate(
        settings,
        candidate.candidate_id,
        actor_role=ActorRole.VALIDATOR,
        actor_id="val-course-admin",
        idempotency_key="idem-drop-1",
    )
    second_result = drop_candidate(
        settings,
        candidate.candidate_id,
        actor_role=ActorRole.VALIDATOR,
        actor_id="val-course-admin",
        idempotency_key="idem-drop-1",
    )

    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_dropped",
    )

    assert second_result == first_result
    assert len(audit_events) == 1
    assert audit_events[0].idempotency_key == "idem-drop-1"


def test_drop_candidate_recovers_when_mark_applied_fails_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-unresolved-integral.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    original_mark_applied = candidate_service.mark_mutation_request_applied
    failed_once = {"value": False}

    def flaky_mark_applied(*args, **kwargs):  # noqa: ANN002, ANN003
        if not failed_once["value"]:
            failed_once["value"] = True
            raise sqlite3.OperationalError("forced mark_applied failure")
        return original_mark_applied(*args, **kwargs)

    monkeypatch.setattr(candidate_service, "mark_mutation_request_applied", flaky_mark_applied)

    with pytest.raises(sqlite3.OperationalError, match="forced mark_applied failure"):
        drop_candidate(
            settings,
            candidate.candidate_id,
            actor_role=ActorRole.VALIDATOR,
            actor_id="val-course-admin",
            idempotency_key="idem-drop-mark-applied",
        )

    mutation_request = get_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_dropped",
        idempotency_key="idem-drop-mark-applied",
    )
    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_dropped",
        idempotency_key="idem-drop-mark-applied",
    )

    assert mutation_request is not None
    assert mutation_request.status == "pending"
    assert len(audit_events) == 1

    recovered_candidate = drop_candidate(
        settings,
        candidate.candidate_id,
        actor_role=ActorRole.VALIDATOR,
        actor_id="val-course-admin",
        idempotency_key="idem-drop-mark-applied",
    )
    mutation_request = get_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_dropped",
        idempotency_key="idem-drop-mark-applied",
    )

    assert recovered_candidate.status is CandidateStatus.DROPPED
    assert mutation_request is not None
    assert mutation_request.status == "applied"


def test_drop_candidate_rejects_timestamp_drift_for_same_idempotency_key(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-unresolved-integral.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    drop_candidate(
        settings,
        candidate.candidate_id,
        actor_role=ActorRole.VALIDATOR,
        actor_id="val-course-admin",
        idempotency_key="idem-drop-time",
        dropped_at=datetime(2026, 4, 8, 12, 20, tzinfo=UTC),
    )

    with pytest.raises(CandidateStateError, match="different request"):
        drop_candidate(
            settings,
            candidate.candidate_id,
            actor_role=ActorRole.VALIDATOR,
            actor_id="val-course-admin",
            idempotency_key="idem-drop-time",
            dropped_at=datetime(2026, 4, 8, 12, 25, tzinfo=UTC),
        )


def test_drop_candidate_rejects_invalid_reason_at_service_boundary(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-unresolved-integral.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    with pytest.raises(CandidateStateError, match="invalid drop reason"):
        drop_candidate(
            settings,
            candidate.candidate_id,
            actor_role=ActorRole.VALIDATOR,
            actor_id="val-course-admin",
            reason="freeform_reason_not_allowed",
        )


def test_drop_candidate_recovers_pending_idempotent_transition(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-unresolved-integral.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    dropped_candidate = candidate.model_copy(
        update={
            "status": CandidateStatus.DROPPED,
            "approved_by": "val-course-admin",
            "approved_at": datetime(2026, 4, 8, 12, 30, tzinfo=UTC),
        }
    )
    candidate_path = candidate_service.find_candidate_path(settings, candidate.candidate_id)
    candidate_service._write_candidate(candidate_path, dropped_candidate)
    begin_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_dropped",
        idempotency_key="idem-drop-ambiguous",
        actor_role=ActorRole.VALIDATOR.value,
        actor_id="val-course-admin",
        request_fingerprint=candidate_service._build_request_fingerprint(
            candidate_id=candidate.candidate_id,
            action="candidate_dropped",
            actor_role=ActorRole.VALIDATOR,
            actor_id="val-course-admin",
            requested_dropped_at=None,
            notes=None,
        ),
        created_at=datetime(2026, 4, 8, 12, 30, tzinfo=UTC),
    )

    recovered_candidate = drop_candidate(
        settings,
        candidate.candidate_id,
        actor_role=ActorRole.VALIDATOR,
        actor_id="val-course-admin",
        idempotency_key="idem-drop-ambiguous",
    )
    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_dropped",
        idempotency_key="idem-drop-ambiguous",
    )

    assert recovered_candidate.status is CandidateStatus.DROPPED
    assert len(audit_events) == 1


def test_drop_candidate_rejects_mismatched_applied_replay(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-unresolved-integral.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    mutation_request = begin_mutation_request(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_dropped",
        idempotency_key="idem-drop-applied-mismatch",
        actor_role=ActorRole.VALIDATOR.value,
        actor_id="val-course-admin",
        request_fingerprint=candidate_service._build_request_fingerprint(
            candidate_id=candidate.candidate_id,
            action="candidate_dropped",
            actor_role=ActorRole.VALIDATOR,
            actor_id="val-course-admin",
            requested_dropped_at=None,
            notes=None,
        ),
        created_at=datetime(2026, 4, 8, 12, 50, tzinfo=UTC),
    )
    mark_mutation_request_applied(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
        action="candidate_dropped",
        idempotency_key="idem-drop-applied-mismatch",
        updated_at=mutation_request.created_at,
    )

    with pytest.raises(CandidateStateError, match="stored dropped candidate does not match"):
        drop_candidate(
            settings,
            candidate.candidate_id,
            actor_role=ActorRole.VALIDATOR,
            actor_id="val-course-admin",
            idempotency_key="idem-drop-applied-mismatch",
        )


def test_student_cannot_drop_candidate(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    with pytest.raises(CandidateStateError, match="not allowed for role student"):
        drop_candidate(
            settings,
            candidate.candidate_id,
            actor_role=ActorRole.STUDENT,
            actor_id="stu-kim-minji",
        )


def test_operator_cannot_drop_operations_candidate(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-operations-refund.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    with pytest.raises(CandidateStateError, match="not allowed for role operator"):
        drop_candidate(
            settings,
            candidate.candidate_id,
            actor_role=ActorRole.OPERATOR,
            actor_id="ops-academic-office",
        )


def test_promote_candidate_requires_open_state(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-operations-refund.json")
    create_candidate(settings, candidate, actor_role=ActorRole.SYSTEM, actor_id="system")
    drop_candidate(
        settings,
        candidate.candidate_id,
        actor_role=ActorRole.VALIDATOR,
        actor_id="val-course-admin",
    )

    with pytest.raises(CandidateStateError):
        promote_candidate(
            settings,
            candidate.candidate_id,
            approved_by="val-course-admin",
            actor_role=ActorRole.VALIDATOR,
            actor_id="val-course-admin",
        )


def test_list_candidates_filters_by_kind_status_and_class(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    faq_candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    misconception_candidate = load_candidate_fixture("open-misconception-chain-rule.json")
    create_candidate(settings, faq_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")
    create_candidate(
        settings,
        misconception_candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system",
    )
    promote_candidate(
        settings,
        faq_candidate.candidate_id,
        approved_by="ins-calculus-team",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
    )

    faq_candidates = list_candidates(settings, kind=faq_candidate.kind)
    promoted_candidates = list_candidates(settings, status=CandidateStatus.PROMOTED)
    unknown_class_candidates = list_candidates(settings, class_id="class-does-not-exist")

    assert [candidate.candidate_id for candidate in faq_candidates] == [faq_candidate.candidate_id]
    assert [candidate.candidate_id for candidate in promoted_candidates] == [
        faq_candidate.candidate_id
    ]
    assert unknown_class_candidates == []


def test_list_candidates_returns_most_recently_updated_first(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    older_candidate = load_candidate_fixture("open-faq-homework-deadline.json").model_copy(
        update={
            "candidate_id": "cand-faq-older",
            "created_at": datetime(2026, 4, 8, 10, 0, tzinfo=UTC),
            "updated_at": datetime(2026, 4, 8, 10, 0, tzinfo=UTC),
        }
    )
    newer_candidate = load_candidate_fixture("open-misconception-chain-rule.json").model_copy(
        update={
            "candidate_id": "cand-misconception-newer",
            "created_at": older_candidate.created_at + timedelta(minutes=5),
            "updated_at": older_candidate.created_at + timedelta(days=1),
        }
    )
    create_candidate(settings, older_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")
    create_candidate(settings, newer_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    candidates = list_candidates(settings)

    assert [candidate.candidate_id for candidate in candidates] == [
        "cand-misconception-newer",
        "cand-faq-older",
    ]


def test_get_candidate_backfills_missing_updated_at_for_legacy_files(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    legacy_candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    candidate_path = candidate_service.build_candidate_path(settings, legacy_candidate)
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_payload = legacy_candidate.model_dump(mode="json", exclude_none=True)
    legacy_payload.pop("updated_at", None)
    candidate_path.write_text(json.dumps(legacy_payload, indent=2) + "\n", encoding="utf-8")

    loaded_candidate = get_candidate(settings, legacy_candidate.candidate_id)
    rewritten_payload = json.loads(candidate_path.read_text(encoding="utf-8"))

    assert loaded_candidate.updated_at == legacy_candidate.created_at
    assert rewritten_payload["updated_at"] == legacy_candidate.created_at.isoformat().replace(
        "+00:00",
        "Z",
    )


def test_get_candidate_returns_legacy_candidate_when_normalization_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    legacy_candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    candidate_path = candidate_service.build_candidate_path(settings, legacy_candidate)
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_payload = legacy_candidate.model_dump(mode="json", exclude_none=True)
    legacy_payload.pop("updated_at", None)
    candidate_path.write_text(json.dumps(legacy_payload, indent=2) + "\n", encoding="utf-8")

    def flaky_write(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise OSError("forced normalization write failure")

    monkeypatch.setattr(candidate_service, "_write_candidate", flaky_write)

    loaded_candidate = get_candidate(settings, legacy_candidate.candidate_id)
    persisted_payload = json.loads(candidate_path.read_text(encoding="utf-8"))

    assert loaded_candidate.updated_at == legacy_candidate.created_at
    assert "updated_at" not in persisted_payload


def test_get_candidate_returns_legacy_candidate_when_normalization_lock_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    legacy_candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    candidate_path = candidate_service.build_candidate_path(settings, legacy_candidate)
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_payload = legacy_candidate.model_dump(mode="json", exclude_none=True)
    legacy_payload.pop("updated_at", None)
    candidate_path.write_text(json.dumps(legacy_payload, indent=2) + "\n", encoding="utf-8")

    def blocked_lock(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise CandidateStateError("candidate changed during transition")

    monkeypatch.setattr(candidate_service, "_acquire_candidate_locks", blocked_lock)

    loaded_candidate = get_candidate(settings, legacy_candidate.candidate_id)
    persisted_payload = json.loads(candidate_path.read_text(encoding="utf-8"))

    assert loaded_candidate.updated_at == legacy_candidate.created_at
    assert "updated_at" not in persisted_payload


def test_promote_candidate_accepts_legacy_snapshot_when_normalization_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    legacy_candidate = load_candidate_fixture("open-faq-homework-deadline.json")
    candidate_path = candidate_service.build_candidate_path(settings, legacy_candidate)
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_payload = legacy_candidate.model_dump(mode="json", exclude_none=True)
    legacy_payload.pop("updated_at", None)
    candidate_path.write_text(json.dumps(legacy_payload, indent=2) + "\n", encoding="utf-8")

    original_write_candidate = candidate_service._write_candidate
    write_attempts = {"count": 0}

    def flaky_then_real_write(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        write_attempts["count"] += 1
        if write_attempts["count"] == 1:
            raise OSError("forced normalization write failure")
        return original_write_candidate(*args, **kwargs)

    monkeypatch.setattr(candidate_service, "_write_candidate", flaky_then_real_write)

    loaded_candidate = get_candidate(settings, legacy_candidate.candidate_id)
    persisted_payload = json.loads(candidate_path.read_text(encoding="utf-8"))

    assert loaded_candidate.updated_at == legacy_candidate.created_at
    assert "updated_at" not in persisted_payload

    promoted_candidate = promote_candidate(
        settings,
        legacy_candidate.candidate_id,
        current_candidate_snapshot=loaded_candidate,
        approved_by="ins-calculus-team",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        related_page_id="page-faq-homework-submission",
    )

    stored_candidate = get_candidate(settings, legacy_candidate.candidate_id)

    assert promoted_candidate.status is CandidateStatus.PROMOTED
    assert stored_candidate.status is CandidateStatus.PROMOTED
    assert stored_candidate.updated_at == promoted_candidate.updated_at


def test_list_candidates_filters_by_class_across_kinds(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    requested_class = "class-calculus-1-2026-spring-a"
    other_class = "class-calculus-1-2026-spring-b"

    same_class_faq = load_candidate_fixture("open-faq-homework-deadline.json")
    same_class_misconception = load_candidate_fixture("open-misconception-chain-rule.json")
    other_class_candidate = load_candidate_fixture("open-operations-refund.json").model_copy(
        update={
            "candidate_id": "cand-operations-other-class",
            "class_id": other_class,
            "course_id": "course-calculus-1",
        }
    )

    create_candidate(settings, same_class_faq, actor_role=ActorRole.SYSTEM, actor_id="system")
    create_candidate(
        settings,
        same_class_misconception,
        actor_role=ActorRole.SYSTEM,
        actor_id="system",
    )
    create_candidate(
        settings,
        other_class_candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system",
    )

    candidates = list_candidates(settings, class_id=requested_class)

    assert {candidate.class_id for candidate in candidates} == {requested_class}
    assert {candidate.candidate_id for candidate in candidates} == {
        same_class_faq.candidate_id,
        same_class_misconception.candidate_id,
    }


def test_build_candidate_search_scopes_uses_structural_paths() -> None:
    candidate_root = Path("C:/tmp/knowloop/data/candidate")

    assert candidate_service._build_candidate_search_scopes(
        candidate_root,
        kind=CandidateKind.FAQ,
        class_id="class-calculus-1-2026-spring-a",
    ) == [
        (
            candidate_root / "faq" / "class-calculus-1-2026-spring-a",
            "*.json",
        )
    ]

    assert candidate_service._build_candidate_search_scopes(
        candidate_root,
        kind=None,
        class_id="class-calculus-1-2026-spring-a",
    ) == [
        (
            candidate_root / "misconceptions" / "class-calculus-1-2026-spring-a",
            "*.json",
        ),
        (
            candidate_root / "faq" / "class-calculus-1-2026-spring-a",
            "*.json",
        ),
        (
            candidate_root / "interventions" / "class-calculus-1-2026-spring-a",
            "*.json",
        ),
        (
            candidate_root / "unresolved-questions" / "class-calculus-1-2026-spring-a",
            "*.json",
        ),
        (
            candidate_root / "operations-notes" / "class-calculus-1-2026-spring-a",
            "*.json",
        ),
    ]

    assert candidate_service._build_candidate_search_scopes(
        candidate_root,
        kind=CandidateKind.MISCONCEPTION,
        class_id=None,
    ) == [
        (
            candidate_root / "misconceptions",
            "*/*.json",
        )
    ]

    assert candidate_service._build_candidate_search_scopes(
        candidate_root,
        kind=None,
        class_id=None,
    ) == [
        (candidate_root / "misconceptions", "*/*.json"),
        (candidate_root / "faq", "*/*.json"),
        (candidate_root / "interventions", "*/*.json"),
        (candidate_root / "unresolved-questions", "*/*.json"),
        (candidate_root / "operations-notes", "*/*.json"),
    ]


def test_list_audit_events_returns_newest_first(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json").model_copy(
        update={
            "created_at": datetime(2026, 4, 8, 10, 0, tzinfo=UTC),
        }
    )
    create_candidate(
        settings,
        candidate,
        actor_role=ActorRole.SYSTEM,
        actor_id="system",
        request_id="req-create-candidate",
    )
    promote_candidate(
        settings,
        candidate.candidate_id,
        approved_by="ins-calculus-team",
        actor_role=ActorRole.INSTRUCTOR,
        actor_id="ins-calculus-team",
        related_page_id="page-faq-homework-submission",
        request_id="req-promote-candidate",
        approved_at=candidate.created_at + timedelta(minutes=10),
    )

    audit_events = list_audit_events(
        settings,
        entity_type="candidate",
        entity_id=candidate.candidate_id,
    )

    assert [event.action for event in audit_events] == [
        "candidate_promoted",
        "candidate_created",
    ]


def test_create_candidate_rolls_back_when_audit_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    candidate = load_candidate_fixture("open-faq-homework-deadline.json").model_copy(
        update={"candidate_id": "cand-faq-audit-failure-create"}
    )

    def fail_audit(*args, **kwargs):  # noqa: ANN002, ANN003
        raise sqlite3.IntegrityError("forced audit failure")

    monkeypatch.setattr(candidate_service, "create_audit_event", fail_audit)

    with pytest.raises(sqlite3.IntegrityError, match="forced audit failure"):
        create_candidate(
            settings,
            candidate,
            actor_role=ActorRole.SYSTEM,
            actor_id="system-seed",
        )

    with pytest.raises(CandidateNotFoundError):
        get_candidate(settings, candidate.candidate_id)


def test_merge_candidate_rolls_back_when_audit_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    canonical_candidate = load_candidate_fixture("open-misconception-chain-rule.json")
    duplicate_candidate = load_candidate_fixture("open-misconception-chain-rule-duplicate.json")
    create_candidate(settings, canonical_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")
    create_candidate(settings, duplicate_candidate, actor_role=ActorRole.SYSTEM, actor_id="system")

    def fail_audit(*args, **kwargs):  # noqa: ANN002, ANN003
        raise sqlite3.IntegrityError("forced audit failure")

    monkeypatch.setattr(candidate_service, "create_audit_event", fail_audit)

    with pytest.raises(sqlite3.IntegrityError, match="forced audit failure"):
        merge_candidate(
            settings,
            duplicate_candidate.candidate_id,
            target_candidate_id=canonical_candidate.candidate_id,
            actor_role=ActorRole.VALIDATOR,
            actor_id="val-course-admin",
            idempotency_key="idem-merge-rollback",
        )

    refreshed_source = get_candidate(settings, duplicate_candidate.candidate_id)
    refreshed_target = get_candidate(settings, canonical_candidate.candidate_id)

    assert refreshed_source.status is CandidateStatus.OPEN
    assert refreshed_source.merged_into is None
    assert refreshed_target.session_refs == canonical_candidate.session_refs


def test_build_audit_event_id_is_unique_within_same_second() -> None:
    timestamp = datetime(2026, 4, 8, 10, 0, 0, 123456, tzinfo=UTC)

    first_event_id = build_audit_event_id(
        action="candidate_promoted",
        entity_id="cand-same-second",
        created_at=timestamp,
    )
    second_event_id = build_audit_event_id(
        action="candidate_promoted",
        entity_id="cand-same-second",
        created_at=timestamp + timedelta(microseconds=1),
    )

    assert first_event_id != second_event_id


def test_create_audit_event_returns_existing_row_on_duplicate_insert(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    created_at = datetime(2026, 4, 8, 13, 0, tzinfo=UTC)

    first_event = create_audit_event(
        settings,
        entity_type="candidate",
        entity_id="cand-duplicate-audit",
        action="candidate_promoted",
        actor_role=ActorRole.INSTRUCTOR.value,
        actor_id="ins-calculus-team",
        from_status=CandidateStatus.OPEN.value,
        to_status=CandidateStatus.PROMOTED.value,
        idempotency_key="idem-audit-dup",
        created_at=created_at,
    )
    second_event = create_audit_event(
        settings,
        entity_type="candidate",
        entity_id="cand-duplicate-audit",
        action="candidate_promoted",
        actor_role=ActorRole.INSTRUCTOR.value,
        actor_id="ins-calculus-team",
        from_status=CandidateStatus.OPEN.value,
        to_status=CandidateStatus.PROMOTED.value,
        idempotency_key="idem-audit-dup",
        created_at=created_at,
    )

    assert second_event == first_event


def test_list_audit_events_uses_stable_tiebreaker_for_equal_timestamps(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)
    created_at = datetime(2026, 4, 8, 13, 30, tzinfo=UTC)

    event_one = create_audit_event(
        settings,
        entity_type="candidate",
        entity_id="cand-order-a",
        action="candidate_created",
        actor_role=ActorRole.SYSTEM.value,
        created_at=created_at,
    )
    event_two = create_audit_event(
        settings,
        entity_type="candidate",
        entity_id="cand-order-b",
        action="candidate_created",
        actor_role=ActorRole.SYSTEM.value,
        created_at=created_at,
    )

    audit_events = list_audit_events(settings, action="candidate_created")

    assert [audit_events[0].event_id, audit_events[1].event_id] == sorted(
        [event_one.event_id, event_two.event_id],
        reverse=True,
    )


def test_get_candidate_raises_for_missing_candidate(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    bootstrap_storage(settings)

    with pytest.raises(CandidateNotFoundError):
        get_candidate(settings, "cand-missing")
