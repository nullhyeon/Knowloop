from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, Field

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole
from knowloop_api.services.candidates import (
    CandidateItem,
    CandidateKind,
    CandidateStatus,
    list_candidates,
)
from knowloop_api.services.learning import LearningNote, get_learning_note
from knowloop_api.services.sessions import (
    SessionInsightRow,
    SessionRecord,
    list_session_insight_rows_for_class,
)

InsightSession = SessionInsightRow | SessionRecord

ACADEMIC_INSIGHT_KINDS = frozenset(
    {
        CandidateKind.FAQ,
        CandidateKind.MISCONCEPTION,
        CandidateKind.INTERVENTION,
        CandidateKind.UNRESOLVED_QUESTION,
    }
)


class InsightTopic(BaseModel):
    topic: str
    session_count: int
    student_count: int


class InsightGap(BaseModel):
    gap: str
    student_count: int


class InsightPattern(BaseModel):
    pattern_id: str
    kind: CandidateKind
    title: str
    summary: str
    related_page_id: str | None = None
    candidate_count: int
    session_count: int
    student_count: int
    latest_created_at: datetime
    candidate_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    max_confidence: float


class InstructorInsightOverview(BaseModel):
    course_id: str
    class_id: str
    student_session_count: int
    unique_student_count: int
    open_candidate_total: int
    candidate_counts: dict[str, int]
    students_with_learning_notes: int
    students_with_open_gaps: int
    top_topics: list[InsightTopic]
    top_gap_clusters: list[InsightGap]
    top_patterns: list[InsightPattern]


@dataclass(slots=True)
class _PatternAggregate:
    kind: CandidateKind
    title: str
    summary: str
    related_page_id: str | None
    latest_created_at: datetime
    max_confidence: float
    candidate_ids: list[str] = field(default_factory=list)
    session_ids: set[str] = field(default_factory=set)
    student_ids: set[str] = field(default_factory=set)
    tags: set[str] = field(default_factory=set)


def build_instructor_overview(
    settings: Settings,
    *,
    course_id: str,
    class_id: str,
) -> InstructorInsightOverview:
    sessions = _load_student_sessions(
        settings,
        course_id=course_id,
        class_id=class_id,
    )
    learning_notes = _load_learning_notes_for_class(
        settings,
        course_id=course_id,
        class_id=class_id,
    )
    open_candidates = _load_open_academic_candidates(
        settings,
        course_id=course_id,
        class_id=class_id,
    )
    top_patterns, _ = list_candidate_patterns(
        settings,
        course_id=course_id,
        class_id=class_id,
        limit=5,
        session_records=sessions,
        open_candidates=open_candidates,
    )

    return InstructorInsightOverview(
        course_id=course_id,
        class_id=class_id,
        student_session_count=len(sessions),
        unique_student_count=len({session.user_id for session in sessions}),
        open_candidate_total=len(open_candidates),
        candidate_counts=_build_candidate_counts(open_candidates),
        students_with_learning_notes=len(learning_notes),
        students_with_open_gaps=sum(1 for note in learning_notes if note.gaps),
        top_topics=_build_topic_summary(sessions)[:5],
        top_gap_clusters=_build_gap_summary(learning_notes)[:5],
        top_patterns=top_patterns,
    )


def list_candidate_patterns(
    settings: Settings,
    *,
    course_id: str,
    class_id: str,
    kind: CandidateKind | None = None,
    limit: int = 20,
    offset: int = 0,
    session_records: list[InsightSession] | None = None,
    open_candidates: list[CandidateItem] | None = None,
) -> tuple[list[InsightPattern], int]:
    sessions = (
        session_records
        if session_records is not None
        else _load_student_sessions(
            settings,
            course_id=course_id,
            class_id=class_id,
        )
    )
    candidates = (
        open_candidates
        if open_candidates is not None
        else _load_open_academic_candidates(
            settings,
            course_id=course_id,
            class_id=class_id,
        )
    )
    if kind is not None:
        candidates = [candidate for candidate in candidates if candidate.kind is kind]

    session_map = {session.session_id: session for session in sessions}
    aggregates: dict[tuple[str, str], _PatternAggregate] = {}
    for candidate in candidates:
        key_suffix = candidate.related_page_id or candidate.title.strip().lower()
        aggregate_key = (candidate.kind.value, key_suffix)
        aggregate = aggregates.get(aggregate_key)
        if aggregate is None:
            aggregate = _PatternAggregate(
                kind=candidate.kind,
                title=candidate.title,
                summary=candidate.summary,
                related_page_id=candidate.related_page_id,
                latest_created_at=candidate.created_at,
                max_confidence=candidate.confidence,
            )
            aggregates[aggregate_key] = aggregate

        aggregate.candidate_ids.append(candidate.candidate_id)
        aggregate.latest_created_at = max(aggregate.latest_created_at, candidate.created_at)
        aggregate.max_confidence = max(aggregate.max_confidence, candidate.confidence)
        aggregate.tags.update(candidate.tags)
        for session_id in candidate.session_refs:
            session = session_map.get(session_id)
            if session is not None:
                aggregate.session_ids.add(session.session_id)
                aggregate.student_ids.add(session.user_id)

    patterns = [
        InsightPattern(
            pattern_id=_build_pattern_id(kind_value, key_suffix),
            kind=aggregate.kind,
            title=aggregate.title,
            summary=aggregate.summary,
            related_page_id=aggregate.related_page_id,
            candidate_count=len(aggregate.candidate_ids),
            session_count=len(aggregate.session_ids),
            student_count=len(aggregate.student_ids),
            latest_created_at=aggregate.latest_created_at,
            candidate_ids=sorted(aggregate.candidate_ids),
            tags=sorted(aggregate.tags),
            max_confidence=aggregate.max_confidence,
        )
        for (kind_value, key_suffix), aggregate in aggregates.items()
    ]
    patterns.sort(
        key=lambda pattern: (
            pattern.candidate_count,
            pattern.student_count,
            pattern.latest_created_at,
            pattern.pattern_id,
        ),
        reverse=True,
    )
    total = len(patterns)
    return patterns[offset : offset + limit], total


def _load_student_sessions(
    settings: Settings,
    *,
    course_id: str,
    class_id: str,
) -> list[SessionInsightRow]:
    return list_session_insight_rows_for_class(
        settings,
        class_id=class_id,
        course_id=course_id,
        role=ActorRole.STUDENT,
    )


def _load_open_academic_candidates(
    settings: Settings,
    *,
    course_id: str,
    class_id: str,
) -> list[CandidateItem]:
    return [
        candidate
        for candidate in list_candidates(
            settings,
            status=CandidateStatus.OPEN,
            class_id=class_id,
        )
        if candidate.course_id == course_id and candidate.kind in ACADEMIC_INSIGHT_KINDS
    ]


def _load_learning_notes_for_class(
    settings: Settings,
    *,
    course_id: str,
    class_id: str,
) -> list[LearningNote]:
    root = settings.data_root / "learning" / "students"
    if not root.exists():
        return []

    notes: list[LearningNote] = []
    for student_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        note = get_learning_note(
            settings,
            student_id=student_dir.name,
            course_id=course_id,
            class_id=class_id,
        )
        if note is not None:
            notes.append(note)
    return notes


def _build_candidate_counts(candidates: list[CandidateItem]) -> dict[str, int]:
    counts = Counter(candidate.kind.value for candidate in candidates)
    return dict(sorted(counts.items()))


def _build_topic_summary(sessions: list[InsightSession]) -> list[InsightTopic]:
    counts: dict[str, tuple[int, set[str]]] = {}
    for session in sessions:
        seen_topics: set[str] = set()
        for tag in session.tags:
            topic = tag.strip().lower()
            if not topic or topic in seen_topics:
                continue
            session_count, student_ids = counts.get(topic, (0, set()))
            student_ids.add(session.user_id)
            counts[topic] = (session_count + 1, student_ids)
            seen_topics.add(topic)

    topics = [
        InsightTopic(
            topic=topic,
            session_count=session_count,
            student_count=len(student_ids),
        )
        for topic, (session_count, student_ids) in counts.items()
    ]
    topics.sort(
        key=lambda item: (item.session_count, item.student_count, item.topic),
        reverse=True,
    )
    return topics


def _build_gap_summary(notes: list[LearningNote]) -> list[InsightGap]:
    counts: dict[str, set[str]] = {}
    for note in notes:
        seen_gaps: set[str] = set()
        for gap in note.gaps:
            normalized_gap = gap.strip()
            if not normalized_gap or normalized_gap in seen_gaps:
                continue
            counts.setdefault(normalized_gap, set()).add(note.student_id)
            seen_gaps.add(normalized_gap)

    gaps = [
        InsightGap(gap=gap, student_count=len(student_ids))
        for gap, student_ids in counts.items()
    ]
    gaps.sort(key=lambda item: (item.student_count, item.gap), reverse=True)
    return gaps


def _build_pattern_id(kind_value: str, key_suffix: str) -> str:
    normalized = key_suffix.lower().replace(" ", "-").replace("/", "-")
    normalized = "".join(
        character
        for character in normalized
        if character.isalnum() or character == "-"
    )
    normalized = normalized.strip("-")
    if not normalized:
        normalized = "pattern"
    return f"ipat-{kind_value}-{normalized}"
