from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import (
    ActorRole,
    validate_actor_id,
    validate_class_id,
    validate_course_id,
)
from knowloop_api.core.frontmatter import build_frontmatter_document, parse_frontmatter_document
from knowloop_api.db.audit import create_audit_event
from knowloop_api.services.candidates import SourceRef


class LearningNote(BaseModel):
    learning_note_id: str
    student_id: str
    course_id: str
    class_id: str
    actor_role: ActorRole = ActorRole.SYSTEM
    concepts: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    flashcards: list[dict[str, str]] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    session_refs: list[str] = Field(default_factory=list)
    summary: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


def get_learning_note(
    settings: Settings,
    *,
    student_id: str,
    course_id: str,
    class_id: str,
) -> LearningNote | None:
    notes_path = build_learning_notes_path(
        settings,
        student_id=student_id,
        course_id=course_id,
        class_id=class_id,
    )
    gaps_path = build_learning_gaps_path(
        settings,
        student_id=student_id,
        course_id=course_id,
        class_id=class_id,
    )
    next_actions_path = build_learning_next_actions_path(
        settings,
        student_id=student_id,
        course_id=course_id,
        class_id=class_id,
    )
    if not notes_path.exists():
        return None

    metadata, notes_body = parse_frontmatter_document(notes_path.read_text(encoding="utf-8"))
    summary, concepts = _parse_notes_body(notes_body)
    gaps = (
        _parse_bullet_markdown(gaps_path.read_text(encoding="utf-8")) if gaps_path.exists() else []
    )
    next_actions = (
        _parse_bullet_markdown(next_actions_path.read_text(encoding="utf-8"))
        if next_actions_path.exists()
        else []
    )

    class_id = str(metadata.get("class_id", ""))
    return LearningNote(
        learning_note_id=str(
            metadata.get(
                "learning_note_id", build_learning_note_id(student_id, course_id, class_id)
            )
        ),
        student_id=str(metadata.get("student_id", student_id)),
        course_id=str(metadata.get("course_id", course_id)),
        class_id=str(metadata.get("class_id", class_id)),
        actor_role=ActorRole(str(metadata.get("actor_role", ActorRole.SYSTEM.value))),
        concepts=concepts,
        gaps=gaps,
        flashcards=list(metadata.get("flashcards_json", [])),
        next_actions=next_actions,
        source_refs=[
            SourceRef.model_validate(item) for item in metadata.get("source_refs_json", [])
        ],
        session_refs=list(metadata.get("session_refs_json", [])),
        summary=summary,
        created_at=_parse_timestamp(str(metadata.get("created_at"))),
        updated_at=(
            _parse_timestamp(str(metadata["updated_at"]))
            if metadata.get("updated_at") is not None
            else None
        ),
    )


def upsert_learning_note(
    settings: Settings,
    note: LearningNote,
    *,
    actor_id: str | None = None,
    request_id: str | None = None,
    notes: str | None = None,
) -> LearningNote:
    validate_actor_id(note.student_id, actor_role=ActorRole.STUDENT)
    validate_course_id(note.course_id)
    validate_class_id(note.class_id)

    existing = get_learning_note(
        settings,
        student_id=note.student_id,
        course_id=note.course_id,
        class_id=note.class_id,
    )
    if existing is None:
        merged = note.model_copy(
            update={
                "updated_at": note.updated_at or note.created_at,
            }
        )
    else:
        merged = existing.model_copy(
            update={
                "class_id": note.class_id,
                "concepts": _merge_unique_strings(existing.concepts, note.concepts),
                "gaps": _merge_unique_strings(existing.gaps, note.gaps),
                "flashcards": _merge_unique_dicts(existing.flashcards, note.flashcards),
                "next_actions": _merge_unique_strings(existing.next_actions, note.next_actions),
                "source_refs": _merge_source_refs(existing.source_refs, note.source_refs),
                "session_refs": _merge_unique_strings(existing.session_refs, note.session_refs),
                "summary": note.summary or existing.summary,
                "updated_at": note.updated_at or note.created_at,
            }
        )

    _write_learning_files(settings, merged)
    create_audit_event(
        settings,
        entity_type="learning_note",
        entity_id=merged.learning_note_id,
        action="learning_generated",
        actor_role=merged.actor_role.value,
        actor_id=actor_id,
        request_id=request_id,
        notes=notes,
        created_at=merged.updated_at or merged.created_at,
    )
    return merged


def build_learning_note_id(student_id: str, course_id: str, class_id: str) -> str:
    normalized_course = course_id.removeprefix("course-")
    normalized_class = class_id.removeprefix("class-")
    return f"learn-{student_id}-{normalized_course}-{normalized_class}"


def build_learning_directory(
    settings: Settings,
    *,
    student_id: str,
    course_id: str,
    class_id: str,
) -> Path:
    return settings.data_root / "learning" / "students" / student_id / course_id / class_id


def build_learning_notes_path(
    settings: Settings,
    *,
    student_id: str,
    course_id: str,
    class_id: str,
) -> Path:
    return (
        build_learning_directory(
            settings,
            student_id=student_id,
            course_id=course_id,
            class_id=class_id,
        )
        / "notes.md"
    )


def build_learning_gaps_path(
    settings: Settings,
    *,
    student_id: str,
    course_id: str,
    class_id: str,
) -> Path:
    return (
        build_learning_directory(
            settings,
            student_id=student_id,
            course_id=course_id,
            class_id=class_id,
        )
        / "gaps.md"
    )


def build_learning_next_actions_path(
    settings: Settings, *, student_id: str, course_id: str, class_id: str
) -> Path:
    return (
        build_learning_directory(
            settings,
            student_id=student_id,
            course_id=course_id,
            class_id=class_id,
        )
        / "next_actions.md"
    )


def _write_learning_files(settings: Settings, note: LearningNote) -> None:
    learning_dir = build_learning_directory(
        settings,
        student_id=note.student_id,
        course_id=note.course_id,
        class_id=note.class_id,
    )
    learning_dir.mkdir(parents=True, exist_ok=True)

    notes_metadata = {
        "learning_note_id": note.learning_note_id,
        "student_id": note.student_id,
        "course_id": note.course_id,
        "class_id": note.class_id,
        "actor_role": note.actor_role.value,
        "created_at": _serialize_timestamp(note.created_at),
        "updated_at": _serialize_timestamp(note.updated_at or note.created_at),
        "source_refs_json": [
            source_ref.model_dump(mode="json", exclude_none=True) for source_ref in note.source_refs
        ],
        "session_refs_json": note.session_refs,
        "flashcards_json": note.flashcards,
    }
    notes_body = _build_notes_body(note.summary, note.concepts)

    build_learning_notes_path(
        settings,
        student_id=note.student_id,
        course_id=note.course_id,
        class_id=note.class_id,
    ).write_text(
        build_frontmatter_document(notes_metadata, notes_body),
        encoding="utf-8",
    )
    build_learning_gaps_path(
        settings,
        student_id=note.student_id,
        course_id=note.course_id,
        class_id=note.class_id,
    ).write_text(
        _build_bullet_markdown("Gaps", note.gaps),
        encoding="utf-8",
    )
    build_learning_next_actions_path(
        settings,
        student_id=note.student_id,
        course_id=note.course_id,
        class_id=note.class_id,
    ).write_text(
        _build_bullet_markdown("Next Actions", note.next_actions),
        encoding="utf-8",
    )


def _build_notes_body(summary: str | None, concepts: list[str]) -> str:
    lines = ["# Learning Notes", ""]
    if summary:
        lines.extend(["## Summary", summary, ""])
    lines.append("## Concepts")
    if concepts:
        lines.extend(f"- {concept}" for concept in concepts)
    else:
        lines.append("- No tracked concepts yet.")
    return "\n".join(lines)


def _parse_notes_body(body: str) -> tuple[str | None, list[str]]:
    summary_lines: list[str] = []
    concepts: list[str] = []
    section: str | None = None
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line == "## Summary":
            section = "summary"
            continue
        if line == "## Concepts":
            section = "concepts"
            continue
        if not line or line == "# Learning Notes":
            continue
        if section == "summary":
            summary_lines.append(line)
            continue
        if section == "concepts" and line.startswith("- "):
            value = line[2:].strip()
            if value and value != "No tracked concepts yet.":
                concepts.append(value)
    summary = " ".join(summary_lines) if summary_lines else None
    return summary, concepts


def _build_bullet_markdown(title: str, items: list[str]) -> str:
    lines = [f"# {title}", ""]
    if items:
        lines.extend(f"- {item}" for item in items)
    else:
        lines.append("- None.")
    return "\n".join(lines).rstrip("\n") + "\n"


def _parse_bullet_markdown(contents: str) -> list[str]:
    values: list[str] = []
    for raw_line in contents.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        value = line[2:].strip()
        if value and value != "None.":
            values.append(value)
    return values


def _merge_unique_strings(base: list[str], extra: list[str]) -> list[str]:
    seen = set(base)
    merged = list(base)
    for item in extra:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


def _merge_unique_dicts(
    base: list[dict[str, str]], extra: list[dict[str, str]]
) -> list[dict[str, str]]:
    merged = list(base)
    seen = {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in base}
    for item in extra:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            merged.append(item)
            seen.add(key)
    return merged


def _merge_source_refs(base: list[SourceRef], extra: list[SourceRef]) -> list[SourceRef]:
    merged = list(base)
    seen = {(item.source_id, item.source_type, item.chunk_id) for item in base}
    for item in extra:
        key = (item.source_id, item.source_type, item.chunk_id)
        if key not in seen:
            merged.append(item)
            seen.add(key)
    return merged


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _serialize_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
