from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import (
    FLEXIBLE_DOMAIN_SOURCE_TYPES,
    ActorRole,
    RequestDomain,
    SourceType,
    resolve_source_domain,
    validate_actor_id,
    validate_class_id,
    validate_course_id,
)
from knowloop_api.core.input_limits import (
    MAX_SOURCE_CONTENT_LENGTH,
    MAX_SOURCE_FILENAME_LENGTH,
    MAX_SOURCE_MIME_TYPE_LENGTH,
    MAX_SOURCE_TAG_LENGTH,
    MAX_SOURCE_TAGS,
    MAX_SOURCE_TITLE_LENGTH,
)
from knowloop_api.db.audit import (
    begin_mutation_request,
    create_audit_event,
    list_audit_events,
    mark_mutation_request_applied,
)
from knowloop_api.db.manifest import (
    RawSourceRecord,
    build_manifest_path,
    get_source_record,
    list_source_records,
    upsert_source_record,
)

REGISTER_REQUEST_ENTITY_TYPE = "source_registration"
REGISTER_REQUEST_ENTITY_ID = "source_store"
REGISTER_ACTION = "source_registered"
SOURCE_STATUS_REGISTERED = "registered"
FILENAME_EXTENSION_BY_MIME_TYPE = {
    "application/json": ".json",
    "text/html": ".html",
    "text/markdown": ".md",
    "text/plain": ".txt",
}
SOURCE_REGISTRATION_LOCK = threading.RLock()
SOURCE_LOCK_STALE_AFTER = timedelta(minutes=5)


class SourceRegistrationInput(BaseModel):
    source_type: SourceType
    title: str = Field(min_length=1)
    content: str = Field(min_length=1, max_length=MAX_SOURCE_CONTENT_LENGTH)
    mime_type: str | None = Field(default=None, max_length=MAX_SOURCE_MIME_TYPE_LENGTH)
    filename: str | None = Field(default=None, max_length=MAX_SOURCE_FILENAME_LENGTH)
    tags: list[str] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        if len(normalized) > MAX_SOURCE_TITLE_LENGTH:
            raise ValueError(f"title must be at most {MAX_SOURCE_TITLE_LENGTH} chars")
        return normalized

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value

    @field_validator("tags")
    @classmethod
    def normalize_and_bound_tags(cls, value: list[str]) -> list[str]:
        normalized_tags: list[str] = []
        seen_tags: set[str] = set()
        for tag in value:
            normalized_tag = tag.strip()
            if not normalized_tag or normalized_tag in seen_tags:
                continue
            if len(normalized_tag) > MAX_SOURCE_TAG_LENGTH:
                raise ValueError(f"tags must be at most {MAX_SOURCE_TAG_LENGTH} chars each")
            normalized_tags.append(normalized_tag)
            seen_tags.add(normalized_tag)
        if len(normalized_tags) > MAX_SOURCE_TAGS:
            raise ValueError(f"tags must contain at most {MAX_SOURCE_TAGS} unique values")
        return normalized_tags


class SourceNotFoundError(FileNotFoundError):
    """Raised when a source record cannot be found in the manifest."""


class SourceStateError(ValueError):
    """Raised when a source registration or lookup violates the contract."""


class SourceLockError(SourceStateError):
    """Raised when source storage is temporarily locked by another writer."""


def register_source(
    settings: Settings,
    registration: SourceRegistrationInput,
    *,
    course_id: str,
    class_id: str,
    actor_role: ActorRole,
    actor_id: str | None,
    domain: RequestDomain | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    created_at: datetime | None = None,
) -> RawSourceRecord:
    if actor_id is None:
        raise SourceStateError("actor_id is required for source registration")

    actor_id = validate_actor_id(actor_id, actor_role=actor_role)
    course_id = validate_course_id(course_id)
    class_id = validate_class_id(class_id)
    resolved_domain = resolve_source_domain(
        registration.source_type,
        actor_role=actor_role,
        requested_domain=domain,
    )
    requested_at = created_at or datetime.now(UTC)
    checksum = build_checksum(registration.content)
    mutation_request = _begin_register_source_request(
        settings,
        source_type=registration.source_type,
        domain=resolved_domain,
        title=registration.title,
        class_id=class_id,
        course_id=course_id,
        actor_role=actor_role,
        actor_id=actor_id,
        checksum=checksum,
        mime_type=registration.mime_type,
        filename=registration.filename,
        tags=normalize_tags(registration.tags),
        idempotency_key=idempotency_key,
        created_at=requested_at,
    )
    registered_at = mutation_request.created_at if mutation_request is not None else requested_at
    source_id = build_source_id(
        registration.source_type,
        class_id=class_id,
        domain=resolved_domain,
        title=registration.title,
        created_at=registered_at,
    )
    source_record = RawSourceRecord(
        source_id=source_id,
        source_type=registration.source_type,
        domain=resolved_domain,
        title=registration.title.strip(),
        class_id=class_id,
        course_id=course_id,
        actor_role=actor_role,
        created_at=registered_at,
        origin_path=build_origin_path(
            registration.source_type,
            class_id=class_id,
            domain=resolved_domain,
            source_id=source_id,
            filename=registration.filename,
            mime_type=registration.mime_type,
        ),
        checksum=checksum,
        status=SOURCE_STATUS_REGISTERED,
        uploaded_by=actor_id,
        mime_type=registration.mime_type,
        filename=registration.filename,
        tags=normalize_tags(registration.tags),
    )
    with SOURCE_REGISTRATION_LOCK:
        replayed_source = _finalize_or_replay_register(
            settings,
            mutation_request=mutation_request,
            idempotency_key=idempotency_key,
            registration=registration,
            actor_id=actor_id,
        )
        if replayed_source is not None:
            return replayed_source

        existing_source = get_source_record(settings, source_record.source_id)
        if existing_source is not None:
            if existing_source == source_record:
                _ensure_source_registered_audit(
                    settings,
                    source_record=existing_source,
                    actor_role=actor_role,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                )
                _mark_register_source_applied(
                    settings,
                    idempotency_key=idempotency_key,
                    updated_at=datetime.now(UTC),
                )
                return existing_source
            raise FileExistsError(f"source_id already exists: {source_record.source_id}")

        source_path = resolve_source_path(settings, source_record.origin_path)
        if source_path.exists():
            if existing_source is None:
                recovered_source = _recover_file_only_source(
                    settings,
                    source_record=source_record,
                    actor_role=actor_role,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                )
                if recovered_source is not None:
                    return recovered_source
                raise FileExistsError(f"source already exists: {source_record.source_id}")
            if existing_source == source_record:
                _ensure_source_registered_audit(
                    settings,
                    source_record=existing_source,
                    actor_role=actor_role,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                )
                _mark_register_source_applied(
                    settings,
                    idempotency_key=idempotency_key,
                    updated_at=datetime.now(UTC),
                )
                return existing_source
            raise FileExistsError(f"source already exists: {source_record.source_id}")

        _apply_source_transaction(
            settings,
            source_record=source_record,
            content=registration.content,
            persist_audit=lambda: create_audit_event(
                settings,
                entity_type="source",
                entity_id=source_record.source_id,
                action=REGISTER_ACTION,
                actor_role=actor_role.value,
                actor_id=actor_id,
                to_status=source_record.status,
                request_id=request_id,
                idempotency_key=idempotency_key,
                created_at=registered_at,
            ),
            mark_applied=lambda: _mark_register_source_applied(
                settings,
                idempotency_key=idempotency_key,
                updated_at=registered_at,
            ),
        )
        return source_record


def get_source(settings: Settings, source_id: str) -> RawSourceRecord:
    source_record = get_source_record(settings, source_id)
    if source_record is None:
        raise SourceNotFoundError(source_id)
    return source_record


def list_sources(
    settings: Settings,
    *,
    course_id: str,
    class_id: str,
    actor_role: ActorRole | None = None,
    requested_domain: RequestDomain | None = None,
    source_type: SourceType | None = None,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[RawSourceRecord], int]:
    filtered_sources = [
        source
        for source in list_source_records(settings)
        if source.course_id == course_id and source.class_id == class_id
    ]
    if actor_role is not None:
        filtered_sources = [
            source
            for source in filtered_sources
            if is_source_visible_to_role(
                source,
                actor_role=actor_role,
                requested_domain=requested_domain,
            )
        ]
    if source_type is not None:
        filtered_sources = [
            source for source in filtered_sources if source.source_type is source_type
        ]
    if q is not None and q.strip():
        query = q.strip().lower()
        filtered_sources = [
            source
            for source in filtered_sources
            if query in source.title.lower()
            or query in (source.filename or "").lower()
            or any(query in tag.lower() for tag in source.tags)
        ]

    filtered_sources = sorted(
        filtered_sources,
        key=lambda source: (source.created_at, source.source_id),
        reverse=True,
    )
    total = len(filtered_sources)
    return filtered_sources[offset : offset + limit], total


def resolve_source_path(settings: Settings, origin_path: str | Path) -> Path:
    path = Path(origin_path)
    if path.parts[:1] == ("data",):
        path = Path(*path.parts[1:])
    resolved_path = (settings.data_root / path).resolve()
    data_root = settings.data_root.resolve()
    try:
        resolved_path.relative_to(data_root)
    except ValueError as exc:
        raise SourceStateError("source path escapes the configured data_root") from exc
    return resolved_path


def source_record_to_response_payload(source_record: RawSourceRecord) -> dict[str, object]:
    return {
        "source_id": source_record.source_id,
        "source_type": source_record.source_type.value,
        "domain": source_record.domain.value,
        "title": source_record.title,
        "class_id": source_record.class_id,
        "course_id": source_record.course_id,
        "actor_role": source_record.actor_role.value,
        "status": source_record.status,
        "stored_path": source_record.origin_path,
        "origin_path": source_record.origin_path,
        "checksum": source_record.checksum,
        "created_at": source_record.created_at.isoformat().replace("+00:00", "Z"),
        "uploaded_by": source_record.uploaded_by,
        "mime_type": source_record.mime_type,
        "filename": source_record.filename,
        "tags": source_record.tags,
        "summary": source_record.summary,
    }


def is_source_visible_to_role(
    source_record: RawSourceRecord,
    *,
    actor_role: ActorRole,
    requested_domain: RequestDomain | None = None,
) -> bool:
    if actor_role in {ActorRole.SYSTEM, ActorRole.VALIDATOR}:
        if requested_domain in {None, RequestDomain.REVIEW}:
            return True
        return source_record.domain is requested_domain
    if actor_role is ActorRole.INSTRUCTOR:
        return source_record.domain is RequestDomain.ACADEMIC
    if actor_role is ActorRole.OPERATOR:
        return source_record.domain is RequestDomain.OPERATIONS
    return False


def build_checksum(contents: str) -> str:
    return "sha256:" + hashlib.sha256(contents.encode("utf-8")).hexdigest()


def build_source_id(
    source_type: SourceType,
    *,
    class_id: str,
    domain: RequestDomain,
    title: str,
    created_at: datetime,
) -> str:
    source_type_token = source_type.value.replace("_", "-")
    title_slug = slugify(title)
    timestamp = created_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    if source_type in FLEXIBLE_DOMAIN_SOURCE_TYPES:
        return (
            f"src-{source_type_token}-{build_domain_id_token(domain)}-"
            f"{class_id}-{title_slug}-{timestamp}"
        )
    return f"src-{source_type_token}-{class_id}-{title_slug}-{timestamp}"


def build_origin_path(
    source_type: SourceType,
    *,
    class_id: str,
    domain: RequestDomain,
    source_id: str,
    filename: str | None,
    mime_type: str | None,
) -> str:
    extension = resolve_extension(filename=filename, mime_type=mime_type)
    source_directory = source_type.value.replace("_", "-")
    if source_type in FLEXIBLE_DOMAIN_SOURCE_TYPES:
        return (
            Path("data")
            / "raw"
            / source_directory
            / domain.value
            / class_id
            / f"{source_id}{extension}"
        ).as_posix()
    return (
        Path("data") / "raw" / source_directory / class_id / f"{source_id}{extension}"
    ).as_posix()


def resolve_extension(*, filename: str | None, mime_type: str | None) -> str:
    if filename:
        suffix = Path(filename).suffix.strip()
        if suffix:
            return suffix if suffix.startswith(".") else f".{suffix}"
    if mime_type and mime_type in FILENAME_EXTENSION_BY_MIME_TYPE:
        return FILENAME_EXTENSION_BY_MIME_TYPE[mime_type]
    return ".txt"


def normalize_tags(tags: list[str]) -> list[str]:
    normalized_tags: list[str] = []
    seen_tags: set[str] = set()
    for tag in tags:
        normalized_tag = tag.strip()
        if not normalized_tag or normalized_tag in seen_tags:
            continue
        normalized_tags.append(normalized_tag)
        seen_tags.add(normalized_tag)
    return normalized_tags


def build_domain_id_token(domain: RequestDomain) -> str:
    if domain is RequestDomain.ACADEMIC:
        return "acad"
    if domain is RequestDomain.OPERATIONS:
        return "ops"
    return domain.value


def slugify(value: str, *, max_length: int = 20, hash_length: int = 8) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:hash_length]
    prefix_budget = max(max_length - hash_length - 1, 1)
    prefix = (normalized or "source")[:prefix_budget].rstrip("-") or "source"
    return f"{prefix}-{digest}"


def _apply_source_transaction(
    settings: Settings,
    *,
    source_record: RawSourceRecord,
    content: str,
    persist_audit,
    mark_applied=None,
) -> None:
    source_path = resolve_source_path(settings, source_record.origin_path)
    manifest_path = build_manifest_path(settings)
    lock_paths = _acquire_locks([source_path, manifest_path])
    try:
        source_snapshot = source_path.read_text(encoding="utf-8") if source_path.exists() else None
        manifest_snapshot = (
            manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else None
        )
        try:
            _write_text_atomically(source_path, content)
            upsert_source_record(settings, source_record)
            persist_audit()
        except Exception:
            _restore_snapshot(source_path, source_snapshot)
            _restore_snapshot(manifest_path, manifest_snapshot)
            raise

        if mark_applied is not None:
            mark_applied()
    finally:
        _release_locks(lock_paths)


def _restore_snapshot(path: Path, snapshot: str | None) -> None:
    if snapshot is None:
        path.unlink(missing_ok=True)
        return
    _write_text_atomically(path, snapshot)


def _write_text_atomically(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f"tmp-{uuid.uuid4().hex[:8]}.swap"
    temp_path.write_text(contents, encoding="utf-8")
    temp_path.replace(path)


def _acquire_locks(paths: list[Path]) -> list[Path]:
    lock_paths: list[Path] = []
    for path in sorted({Path(item) for item in paths}, key=str):
        path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
        lock_path = path.parent / f".lock-{digest}"
        try:
            with lock_path.open("x", encoding="utf-8") as handle:
                handle.write(path.name)
        except FileExistsError as exc:
            if _try_clear_stale_lock(lock_path):
                try:
                    with lock_path.open("x", encoding="utf-8") as handle:
                        handle.write(path.name)
                except FileExistsError as retry_exc:
                    _release_locks(lock_paths)
                    raise SourceLockError("source storage is busy, retry later") from retry_exc
            else:
                _release_locks(lock_paths)
                raise SourceLockError("source storage is busy, retry later") from exc
        lock_paths.append(lock_path)
    return lock_paths


def _release_locks(lock_paths: list[Path]) -> None:
    for lock_path in lock_paths:
        lock_path.unlink(missing_ok=True)


def _try_clear_stale_lock(lock_path: Path) -> bool:
    try:
        modified_at = datetime.fromtimestamp(lock_path.stat().st_mtime, tz=UTC)
    except FileNotFoundError:
        return True

    if datetime.now(UTC) - modified_at <= SOURCE_LOCK_STALE_AFTER:
        return False

    try:
        lock_path.unlink()
    except FileNotFoundError:
        return True
    return True


def _build_request_fingerprint(**payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _build_register_request_fingerprint(
    source_record: RawSourceRecord,
    *,
    actor_id: str | None,
) -> str:
    return _build_request_fingerprint(
        source_type=source_record.source_type.value,
        domain=source_record.domain.value,
        title=source_record.title,
        class_id=source_record.class_id,
        course_id=source_record.course_id,
        actor_role=source_record.actor_role.value,
        actor_id=actor_id,
        checksum=source_record.checksum,
        mime_type=source_record.mime_type,
        filename=source_record.filename,
        tags=source_record.tags,
    )


def _begin_register_source_request(
    settings: Settings,
    *,
    source_type: SourceType,
    domain: RequestDomain,
    title: str,
    class_id: str,
    course_id: str,
    actor_role: ActorRole,
    actor_id: str | None,
    checksum: str,
    mime_type: str | None,
    filename: str | None,
    tags: list[str],
    idempotency_key: str | None,
    created_at: datetime,
):
    if idempotency_key is None:
        return None

    request_fingerprint = _build_request_fingerprint(
        source_type=source_type.value,
        domain=domain.value,
        title=title.strip(),
        class_id=class_id,
        course_id=course_id,
        actor_role=actor_role.value,
        actor_id=actor_id,
        checksum=checksum,
        mime_type=mime_type,
        filename=filename,
        tags=tags,
    )
    mutation_request = begin_mutation_request(
        settings,
        entity_type=REGISTER_REQUEST_ENTITY_TYPE,
        entity_id=REGISTER_REQUEST_ENTITY_ID,
        action=REGISTER_ACTION,
        idempotency_key=idempotency_key,
        actor_role=actor_role.value,
        actor_id=actor_id,
        request_fingerprint=request_fingerprint,
        created_at=created_at,
    )
    if mutation_request.request_fingerprint != request_fingerprint:
        raise SourceStateError("idempotency_key already exists for a different request")
    return mutation_request


def _mark_register_source_applied(
    settings: Settings,
    *,
    idempotency_key: str | None,
    updated_at: datetime,
) -> None:
    if idempotency_key is None:
        return

    mark_mutation_request_applied(
        settings,
        entity_type=REGISTER_REQUEST_ENTITY_TYPE,
        entity_id=REGISTER_REQUEST_ENTITY_ID,
        action=REGISTER_ACTION,
        idempotency_key=idempotency_key,
        updated_at=updated_at,
    )


def _finalize_or_replay_register(
    settings: Settings,
    *,
    mutation_request,
    idempotency_key: str | None,
    registration: SourceRegistrationInput,
    actor_id: str | None,
) -> RawSourceRecord | None:
    if mutation_request is None or idempotency_key is None:
        return None

    audit_events = list_audit_events(
        settings,
        entity_type="source",
        action=REGISTER_ACTION,
        idempotency_key=idempotency_key,
    )
    if not audit_events:
        return None
    if len(audit_events) > 1:
        raise SourceStateError("stored source replay is ambiguous")

    source_id = audit_events[0].entity_id
    stored_source = get_source(settings, source_id)
    source_path = resolve_source_path(settings, stored_source.origin_path)
    if not source_path.exists():
        raise SourceStateError("stored source does not match the idempotent request")

    expected_fingerprint = _build_register_request_fingerprint(
        stored_source,
        actor_id=actor_id,
    )
    actual_checksum = build_checksum(registration.content)
    if actual_checksum != stored_source.checksum:
        raise SourceStateError("stored source does not match the idempotent request")
    if expected_fingerprint != mutation_request.request_fingerprint:
        raise SourceStateError("stored source does not match the idempotent request")

    _mark_register_source_applied(
        settings,
        idempotency_key=idempotency_key,
        updated_at=datetime.now(UTC),
    )
    return stored_source


def _ensure_source_registered_audit(
    settings: Settings,
    *,
    source_record: RawSourceRecord,
    actor_role: ActorRole,
    actor_id: str | None,
    request_id: str | None,
    idempotency_key: str | None,
) -> None:
    audit_events = list_audit_events(
        settings,
        entity_type="source",
        entity_id=source_record.source_id,
        action=REGISTER_ACTION,
    )
    if audit_events:
        return

    create_audit_event(
        settings,
        entity_type="source",
        entity_id=source_record.source_id,
        action=REGISTER_ACTION,
        actor_role=actor_role.value,
        actor_id=actor_id,
        to_status=source_record.status,
        notes="Recovered missing source_registered audit from existing source file.",
        request_id=request_id,
        idempotency_key=idempotency_key,
        created_at=source_record.created_at,
    )


def _recover_file_only_source(
    settings: Settings,
    *,
    source_record: RawSourceRecord,
    actor_role: ActorRole,
    actor_id: str | None,
    request_id: str | None,
    idempotency_key: str | None,
) -> RawSourceRecord | None:
    source_path = resolve_source_path(settings, source_record.origin_path)
    manifest_path = build_manifest_path(settings)
    lock_paths = _acquire_locks([source_path, manifest_path])
    try:
        if get_source_record(settings, source_record.source_id) is not None:
            return get_source(settings, source_record.source_id)
        if not source_path.exists():
            return None
        if build_checksum(source_path.read_text(encoding="utf-8")) != source_record.checksum:
            return None

        upsert_source_record(settings, source_record)
        _ensure_source_registered_audit(
            settings,
            source_record=source_record,
            actor_role=actor_role,
            actor_id=actor_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
        _mark_register_source_applied(
            settings,
            idempotency_key=idempotency_key,
            updated_at=datetime.now(UTC),
        )
        return source_record
    finally:
        _release_locks(lock_paths)
