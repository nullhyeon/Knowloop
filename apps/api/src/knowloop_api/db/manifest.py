from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole, RequestDomain, SourceType

DEFAULT_MANIFEST_VERSION = 1
DEFAULT_WORKSPACE = "knowloop"
DEFAULT_DESCRIPTION = "Initial backend manifest for Knowloop data layers."


class RawSourceRecord(BaseModel):
    source_id: str
    source_type: SourceType
    domain: RequestDomain
    title: str
    class_id: str
    course_id: str
    actor_role: ActorRole
    created_at: datetime
    origin_path: str
    checksum: str
    status: str
    uploaded_by: str | None = None
    mime_type: str | None = None
    filename: str | None = None
    tags: list[str] = Field(default_factory=list)
    summary: str | None = None


class WorkspaceManifest(BaseModel):
    version: int = DEFAULT_MANIFEST_VERSION
    workspace: str = DEFAULT_WORKSPACE
    description: str = DEFAULT_DESCRIPTION
    generated_at: datetime | None = None
    sources: list[RawSourceRecord] = Field(default_factory=list)


def build_manifest_path(settings: Settings) -> Path:
    return settings.meta_root / "manifest.json"


def ensure_manifest_exists(settings: Settings) -> None:
    manifest_path = build_manifest_path(settings)
    if manifest_path.exists():
        return
    write_manifest(settings, build_default_manifest())


def build_default_manifest() -> WorkspaceManifest:
    return WorkspaceManifest()


def load_manifest(settings: Settings) -> WorkspaceManifest:
    ensure_manifest_exists(settings)
    manifest_path = build_manifest_path(settings)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return WorkspaceManifest.model_validate(payload)


def save_manifest(settings: Settings, manifest: WorkspaceManifest) -> WorkspaceManifest:
    normalized_manifest = manifest.model_copy(
        update={
            "generated_at": datetime.now(UTC),
            "sources": sorted(
                manifest.sources,
                key=lambda source: (source.created_at, source.source_id),
                reverse=True,
            ),
        }
    )
    write_manifest(settings, normalized_manifest)
    return normalized_manifest


def upsert_source_record(
    settings: Settings,
    source_record: RawSourceRecord,
) -> WorkspaceManifest:
    manifest = load_manifest(settings)
    updated_sources: list[RawSourceRecord] = []
    replaced = False
    for existing_source in manifest.sources:
        if existing_source.source_id == source_record.source_id:
            updated_sources.append(source_record)
            replaced = True
            continue
        updated_sources.append(existing_source)
    if not replaced:
        updated_sources.append(source_record)
    return save_manifest(
        settings,
        manifest.model_copy(update={"sources": updated_sources}),
    )


def list_source_records(settings: Settings) -> list[RawSourceRecord]:
    return load_manifest(settings).sources


def get_source_record(settings: Settings, source_id: str) -> RawSourceRecord | None:
    manifest = load_manifest(settings)
    for source in manifest.sources:
        if source.source_id == source_id:
            return source
    return None


def manifest_status(settings: Settings) -> str:
    manifest_path = build_manifest_path(settings)
    if not manifest_path.exists():
        return "missing"
    try:
        load_manifest(settings)
        return "ok"
    except (OSError, ValidationError, json.JSONDecodeError):
        return "missing"


def write_manifest(settings: Settings, manifest: WorkspaceManifest) -> None:
    manifest_path = build_manifest_path(settings)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        manifest.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        indent=2,
    )
    _write_text_atomically(manifest_path, payload + "\n")


def _write_text_atomically(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".tmp-{uuid.uuid4().hex[:8]}"
    temp_path.write_text(contents, encoding="utf-8")
    temp_path.replace(path)
