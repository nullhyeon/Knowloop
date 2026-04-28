from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import (
    ActorRole,
    RequestDomain,
    validate_actor_id,
    validate_class_id,
    validate_course_id,
)
from knowloop_api.core.frontmatter import build_frontmatter_document, parse_frontmatter_document
from knowloop_api.db.audit import create_audit_event
from knowloop_api.services.candidates import SourceRef
from knowloop_api.services.sessions import get_session
from knowloop_api.services.wiki import WikiPageMatch, search_wiki_pages


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


class LearningSummary(BaseModel):
    concept_count: int
    confusion_signal_count: int
    gap_count: int
    next_action_count: int
    session_ref_count: int
    source_ref_count: int
    related_wiki_count: int
    updated_at: str | None = None


class LearningConfusionSignal(BaseModel):
    signal_id: str
    title: str
    summary: str
    session_ref_count: int = 0
    state: str
    linked_session_id: str | None = None


class LearningNoteCard(BaseModel):
    note_id: str
    title: str
    summary: str
    linked_session_id: str | None = None
    linked_session_title: str | None = None
    updated_at: str
    focus_label: str
    next_action_label: str


class LearningGapCard(BaseModel):
    title: str
    description: str
    severity: str


class LearningActionItem(BaseModel):
    title: str
    description: str
    target_kind: str
    target_id: str | None = None


class LearningRelatedWikiLink(BaseModel):
    item_id: str
    page_id: str
    title: str
    summary: str
    reason: str


class LearningRecentSession(BaseModel):
    session_id: str
    title: str
    preview: str
    created_at: str
    tags: list[str] = Field(default_factory=list)
    state_label: str


class LearningConsolePayload(BaseModel):
    summary: LearningSummary
    learning_note: LearningNote | None = None
    confusion_signals: list[LearningConfusionSignal] = Field(default_factory=list)
    learning_notes: list[LearningNoteCard] = Field(default_factory=list)
    gaps: list[LearningGapCard] = Field(default_factory=list)
    next_actions: list[LearningActionItem] = Field(default_factory=list)
    related_wiki: list[LearningRelatedWikiLink] = Field(default_factory=list)
    recent_sessions: list[LearningRecentSession] = Field(default_factory=list)


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
    if not _metadata_matches_learning_scope(
        metadata,
        student_id=student_id,
        course_id=course_id,
        class_id=class_id,
    ):
        return None
    summary, concepts = _parse_notes_body(notes_body)
    gaps = (
        _parse_bullet_markdown(gaps_path.read_text(encoding="utf-8")) if gaps_path.exists() else []
    )
    next_actions = (
        _parse_bullet_markdown(next_actions_path.read_text(encoding="utf-8"))
        if next_actions_path.exists()
        else []
    )

    resolved_class_id = str(metadata.get("class_id", ""))
    return LearningNote(
        learning_note_id=str(
            metadata.get(
                "learning_note_id",
                build_learning_note_id(student_id, course_id, resolved_class_id),
            )
        ),
        student_id=str(metadata.get("student_id", student_id)),
        course_id=str(metadata.get("course_id", course_id)),
        class_id=str(metadata.get("class_id", resolved_class_id)),
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


def build_learning_console_payload(
    settings: Settings,
    *,
    student_id: str,
    course_id: str,
    class_id: str,
) -> LearningConsolePayload:
    note = get_learning_note(
        settings,
        student_id=student_id,
        course_id=course_id,
        class_id=class_id,
    )
    if note is None:
        return LearningConsolePayload(
            summary=LearningSummary(
                concept_count=0,
                confusion_signal_count=0,
                gap_count=0,
                next_action_count=0,
                session_ref_count=0,
                source_ref_count=0,
                related_wiki_count=0,
                updated_at=None,
            )
        )

    visible_session_refs = _filter_learning_session_refs(
        settings,
        note.session_refs,
        student_id=student_id,
        course_id=course_id,
        class_id=class_id,
    )
    visible_note = note.model_copy(
        update={
            "learning_note_id": build_learning_note_id(student_id, course_id, class_id),
            "student_id": student_id,
            "course_id": course_id,
            "class_id": class_id,
            "session_refs": visible_session_refs,
        }
    )

    related_wiki = _build_related_wiki_links(
        settings,
        note=visible_note,
        course_id=course_id,
        class_id=class_id,
    )
    confusion_signals = _build_confusion_signals(visible_note)
    learning_notes = _build_learning_note_cards(settings, visible_note)
    gaps = _build_gap_cards(visible_note)
    next_actions = _build_next_action_items(visible_note)
    recent_sessions = _build_recent_sessions(settings, visible_note)

    return LearningConsolePayload(
        summary=LearningSummary(
            concept_count=len(visible_note.concepts),
            confusion_signal_count=len(confusion_signals),
            gap_count=len(gaps),
            next_action_count=len(next_actions),
            session_ref_count=len(visible_note.session_refs),
            source_ref_count=len(visible_note.source_refs),
            related_wiki_count=len(related_wiki),
            updated_at=_serialize_timestamp(visible_note.updated_at or visible_note.created_at),
        ),
        learning_note=visible_note,
        confusion_signals=confusion_signals,
        learning_notes=learning_notes,
        gaps=gaps,
        next_actions=next_actions,
        related_wiki=related_wiki,
        recent_sessions=recent_sessions,
    )


def upsert_learning_note(
    settings: Settings,
    note: LearningNote,
    *,
    actor_id: str | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
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
        merged = note.model_copy(update={"updated_at": note.updated_at or note.created_at})
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
        if merged == existing:
            return existing

    _write_learning_files(settings, merged)
    create_audit_event(
        settings,
        entity_type="learning_note",
        entity_id=merged.learning_note_id,
        action="learning_generated",
        actor_role=merged.actor_role.value,
        actor_id=actor_id,
        request_id=request_id,
        idempotency_key=idempotency_key,
        notes=notes,
        created_at=merged.updated_at or merged.created_at,
    )
    return merged


def build_learning_note_id(student_id: str, course_id: str, class_id: str) -> str:
    normalized_course = course_id.removeprefix("course-")
    normalized_class = class_id.removeprefix("class-")
    return f"learn-{student_id}-{normalized_course}-{normalized_class}"


def _metadata_matches_learning_scope(
    metadata: dict[str, object],
    *,
    student_id: str,
    course_id: str,
    class_id: str,
) -> bool:
    expected_scope = {
        "student_id": student_id,
        "course_id": course_id,
        "class_id": class_id,
    }
    return all(
        metadata.get(field) is None or str(metadata[field]) == expected
        for field, expected in expected_scope.items()
    )


def _filter_learning_session_refs(
    settings: Settings,
    session_refs: list[str],
    *,
    student_id: str,
    course_id: str,
    class_id: str,
) -> list[str]:
    filtered: list[str] = []
    seen: set[str] = set()
    for session_id in session_refs:
        if session_id in seen:
            continue
        try:
            session = get_session(settings, session_id)
        except Exception:
            continue
        if (
            session.role == ActorRole.STUDENT
            and session.user_id == student_id
            and session.course_id == course_id
            and session.class_id == class_id
        ):
            filtered.append(session_id)
            seen.add(session_id)
    return filtered


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
        / "next_actions.md"
    )


def _build_confusion_signals(note: LearningNote) -> list[LearningConfusionSignal]:
    signals: list[LearningConfusionSignal] = []
    linked_session_id = note.session_refs[0] if note.session_refs else None
    for index, gap in enumerate(note.gaps, start=1):
        signals.append(
            LearningConfusionSignal(
                signal_id=f"{note.learning_note_id}-signal-{index}",
                title=_build_gap_title(gap, index=index),
                summary=gap,
                session_ref_count=len(note.session_refs),
                state="needs_review" if index == 1 else "watch",
                linked_session_id=linked_session_id,
            )
        )
    return signals


def _build_learning_note_cards(settings: Settings, note: LearningNote) -> list[LearningNoteCard]:
    linked_session_id = note.session_refs[0] if note.session_refs else None
    return [
        LearningNoteCard(
            note_id=note.learning_note_id,
            title=note.summary or "Latest learning note",
            summary=_build_note_card_summary(note),
            linked_session_id=linked_session_id,
            linked_session_title=_resolve_session_title(settings, linked_session_id)
            if linked_session_id
            else None,
            updated_at=_serialize_timestamp(note.updated_at or note.created_at),
            focus_label=note.concepts[0] if note.concepts else "Learning note",
            next_action_label="Open next action",
        )
    ]


def _build_gap_cards(note: LearningNote) -> list[LearningGapCard]:
    cards: list[LearningGapCard] = []
    for index, gap in enumerate(note.gaps, start=1):
        cards.append(
            LearningGapCard(
                title=_build_gap_title(gap, index=index),
                description=gap,
                severity="focus" if index == 1 else "watch",
            )
        )
    return cards


def _build_next_action_items(note: LearningNote) -> list[LearningActionItem]:
    items: list[LearningActionItem] = []
    for action in note.next_actions:
        target_kind = "wiki" if _looks_like_wiki_action(action) else "ask"
        items.append(
            LearningActionItem(
                title=action,
                description=note.summary or "Continue from the most recent confusion signal.",
                target_kind=target_kind,
                target_id=None,
            )
        )
    return items


def _build_related_wiki_links(
    settings: Settings,
    *,
    note: LearningNote,
    course_id: str,
    class_id: str,
) -> list[LearningRelatedWikiLink]:
    ranked_pages: list[WikiPageMatch] = []
    seen_page_ids: set[str] = set()
    query_terms = [*note.concepts, *note.gaps, note.summary or ""]

    for term in query_terms:
        normalized_term = term.strip()
        if not normalized_term:
            continue
        for match in search_wiki_pages(
            settings,
            role=ActorRole.STUDENT,
            course_id=course_id,
            class_id=class_id,
            requested_domain=RequestDomain.ACADEMIC,
            message=normalized_term,
            limit=4,
        ):
            if match.page.page_id in seen_page_ids:
                continue
            ranked_pages.append(match)
            seen_page_ids.add(match.page.page_id)
            if len(ranked_pages) >= 4:
                break
        if len(ranked_pages) >= 4:
            break

    return [
        LearningRelatedWikiLink(
            item_id=f"wiki-{match.page.page_id}",
            page_id=match.page.page_id,
            title=match.page.title,
            summary=match.page.summary,
            reason=(
                "Recommended because this page overlaps with the learner's "
                "current concepts or gaps."
            ),
        )
        for match in ranked_pages
    ]


def _build_recent_sessions(settings: Settings, note: LearningNote) -> list[LearningRecentSession]:
    sessions: list[LearningRecentSession] = []
    for session_id in note.session_refs[:3]:
        try:
            session = get_session(settings, session_id)
        except Exception:
            continue
        preview = session.answer.strip().replace("\n", " ")
        if len(preview) > 120:
            preview = f"{preview[:119]}..."
        sessions.append(
            LearningRecentSession(
                session_id=session.session_id,
                title=_resolve_session_title(settings, session.session_id) or "Recent session",
                preview=preview,
                created_at=_serialize_timestamp(session.created_at),
                tags=session.tags,
                state_label="Recent answer",
            )
        )
    return sessions


def _build_gap_title(gap: str, *, index: int) -> str:
    cleaned = gap.rstrip(".")
    if len(cleaned) <= 42:
        return cleaned
    return f"Gap {index}"


def _build_note_card_summary(note: LearningNote) -> str:
    if note.summary:
        return note.summary
    if note.gaps:
        return note.gaps[0]
    if note.concepts:
        return f"Reviewing {note.concepts[0]} should reduce the current confusion."
    return "Learning note generated from recent grounded questions."


def _looks_like_wiki_action(action: str) -> bool:
    lowered = action.lower()
    return (
        "wiki" in lowered
        or "review" in lowered
        or "concept" in lowered
        or "위키" in action
        or "개념" in action
    )


def _resolve_session_title(settings: Settings, session_id: str | None) -> str | None:
    if not session_id:
        return None
    try:
        session = get_session(settings, session_id)
    except Exception:
        return None
    question = session.question.strip().replace("\n", " ")
    if len(question) <= 56:
        return question
    return f"{question[:55]}..."


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
    ).write_text(build_frontmatter_document(notes_metadata, notes_body), encoding="utf-8")
    build_learning_gaps_path(
        settings,
        student_id=note.student_id,
        course_id=note.course_id,
        class_id=note.class_id,
    ).write_text(_build_bullet_markdown("Gaps", note.gaps), encoding="utf-8")
    build_learning_next_actions_path(
        settings,
        student_id=note.student_id,
        course_id=note.course_id,
        class_id=note.class_id,
    ).write_text(_build_bullet_markdown("Next Actions", note.next_actions), encoding="utf-8")


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
