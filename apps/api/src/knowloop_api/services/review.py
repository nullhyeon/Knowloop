from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from knowloop_api.api.context import RequestContext
from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole, RequestDomain
from knowloop_api.core.frontmatter import build_frontmatter_document
from knowloop_api.db.audit import create_audit_event, list_audit_events
from knowloop_api.services.candidates import (
    CandidateItem,
    CandidateKind,
    CandidateStatus,
    drop_candidate,
    get_candidate,
    list_candidates,
    merge_candidate,
    promote_candidate,
)
from knowloop_api.services.sources import SourceNotFoundError, get_source, resolve_source_path
from knowloop_api.services.wiki import get_wiki_page

ACADEMIC_REVIEW_KINDS = frozenset(
    {
        CandidateKind.MISCONCEPTION,
        CandidateKind.FAQ,
        CandidateKind.INTERVENTION,
        CandidateKind.UNRESOLVED_QUESTION,
    }
)
WIKI_SYNC_PENDING_ACTION = "candidate_wiki_sync_pending"
WIKI_SYNC_COMPLETED_ACTION = "candidate_wiki_synced"
WIKI_DOMAIN_BY_KIND = {
    CandidateKind.FAQ: "faq",
    CandidateKind.MISCONCEPTION: "misconceptions",
    CandidateKind.INTERVENTION: "concepts",
    CandidateKind.UNRESOLVED_QUESTION: "concepts",
    CandidateKind.OPERATIONS_NOTE: "operations",
}
REVIEWABLE_ROLES = frozenset(
    {
        ActorRole.INSTRUCTOR,
        ActorRole.OPERATOR,
        ActorRole.VALIDATOR,
        ActorRole.SYSTEM,
    }
)


class ReviewStateError(ValueError):
    """Raised when a review request violates workflow expectations."""


class ForbiddenReviewScopeError(ReviewStateError):
    """Raised when the current role cannot access the requested review scope."""


class ReviewPatchRequest(BaseModel):
    target_page_id: str | None = None
    target_path: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def ensure_target_hint(self) -> "ReviewPatchRequest":
        if not self.target_page_id and not self.target_path:
            raise ValueError("target_page_id or target_path is required")
        return self


class ReviewApproveRequest(BaseModel):
    target_page_id: str | None = None
    target_path: str | None = None
    approval_notes: str | None = None

    @model_validator(mode="after")
    def ensure_target_hint(self) -> "ReviewApproveRequest":
        if not self.target_page_id and not self.target_path:
            raise ValueError("target_page_id or target_path is required")
        return self


class ReviewMergeRequest(BaseModel):
    target_candidate_id: str
    merge_notes: str | None = None


class ReviewDropRequest(BaseModel):
    reason: str = Field(min_length=1)
    drop_notes: str | None = None


class ReviewCandidateDetail(BaseModel):
    candidate: dict[str, object]
    audit_events: list[dict[str, object]]
    available_actions: list[str]


class ReviewPatchPreview(BaseModel):
    candidate: dict[str, object]
    patch: dict[str, object]
    before_markdown: str | None = None
    after_markdown: str


class ReviewActionResponse(BaseModel):
    candidate: dict[str, object]
    patch: dict[str, object] | None = None
    target_candidate: dict[str, object] | None = None
    wiki_page: dict[str, object] | None = None


@dataclass(slots=True)
class WikiPatchDraft:
    patch_payload: dict[str, object]
    before_markdown: str | None
    after_markdown: str
    target_page_id: str
    target_path: Path
    operation: str


def list_review_candidates(
    settings: Settings,
    *,
    context: RequestContext,
    status: CandidateStatus | None = CandidateStatus.OPEN,
    kind: CandidateKind | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, object]], int]:
    _assert_review_role(context)
    visible_candidates = [
        candidate_to_payload(candidate)
        for candidate in list_candidates(
            settings,
            kind=kind,
            status=status,
            class_id=context.class_id,
        )
        if _is_candidate_visible(candidate, context=context)
        and candidate.course_id == context.course_id
    ]
    total = len(visible_candidates)
    return visible_candidates[offset : offset + limit], total


def get_review_candidate_detail(
    settings: Settings,
    *,
    candidate_id: str,
    context: RequestContext,
) -> ReviewCandidateDetail:
    candidate = _load_visible_candidate(settings, candidate_id=candidate_id, context=context)
    audit_events = [
        {
            "event_id": event.event_id,
            "action": event.action,
            "actor_role": event.actor_role,
            "actor_id": event.actor_id,
            "from_status": event.from_status,
            "to_status": event.to_status,
            "notes": event.notes,
            "request_id": event.request_id,
            "idempotency_key": event.idempotency_key,
            "created_at": event.created_at.isoformat().replace("+00:00", "Z"),
        }
        for event in list_audit_events(
            settings,
            entity_type="candidate",
            entity_id=candidate.candidate_id,
        )
    ]
    return ReviewCandidateDetail(
        candidate=candidate_to_payload(candidate),
        audit_events=audit_events,
        available_actions=_available_actions(candidate, context=context),
    )


def preview_candidate_patch(
    settings: Settings,
    *,
    candidate_id: str,
    payload: ReviewPatchRequest,
    context: RequestContext,
) -> ReviewPatchPreview:
    candidate = _load_visible_candidate(settings, candidate_id=candidate_id, context=context)
    patch_draft = _build_patch_draft(
        settings,
        candidate=candidate,
        context=context,
        target_page_id=payload.target_page_id,
        target_path=payload.target_path,
        notes=payload.notes,
        approval_status="draft",
        approved_by=None,
        approved_at=None,
    )
    return ReviewPatchPreview(
        candidate=candidate_to_payload(candidate),
        patch=patch_draft.patch_payload,
        before_markdown=patch_draft.before_markdown,
        after_markdown=patch_draft.after_markdown,
    )


def approve_candidate(
    settings: Settings,
    *,
    candidate_id: str,
    payload: ReviewApproveRequest,
    context: RequestContext,
) -> ReviewActionResponse:
    if context.idempotency_key is None or not context.idempotency_key.strip():
        raise ReviewStateError("Idempotency-Key is required for candidate approval")

    candidate = _load_visible_candidate(settings, candidate_id=candidate_id, context=context)
    _assert_action_allowed(candidate, context=context, action="approve")
    target_page_id = payload.target_page_id or candidate.related_page_id
    if target_page_id is None:
        raise ReviewStateError("candidate approval requires a target_page_id")
    promoted_candidate = promote_candidate(
        settings,
        candidate_id,
        approved_by=context.actor_id,
        actor_role=context.role,
        actor_id=context.actor_id,
        related_page_id=target_page_id,
        request_id=context.request_id,
        idempotency_key=context.idempotency_key,
        notes=payload.approval_notes,
    )
    patch_draft = _build_patch_draft(
        settings,
        candidate=promoted_candidate,
        context=context,
        target_page_id=promoted_candidate.related_page_id,
        target_path=payload.target_path,
        notes=payload.approval_notes,
        approval_status="approved",
        approved_by=context.actor_id,
        approved_at=promoted_candidate.approved_at,
    )
    create_audit_event(
        settings,
        entity_type="candidate",
        entity_id=promoted_candidate.candidate_id,
        action=WIKI_SYNC_PENDING_ACTION,
        actor_role=context.role.value,
        actor_id=context.actor_id,
        request_id=context.request_id,
        idempotency_key=context.idempotency_key,
        created_at=promoted_candidate.approved_at,
        notes="Candidate promotion is waiting for wiki patch application.",
    )
    _write_wiki_page(patch_draft.target_path, patch_draft.after_markdown)
    create_audit_event(
        settings,
        entity_type="wiki_page",
        entity_id=patch_draft.target_page_id,
        action="wiki_patch_applied",
        actor_role=context.role.value,
        actor_id=context.actor_id,
        request_id=context.request_id,
        idempotency_key=context.idempotency_key,
        created_at=promoted_candidate.approved_at,
        notes=payload.approval_notes,
    )
    create_audit_event(
        settings,
        entity_type="candidate",
        entity_id=promoted_candidate.candidate_id,
        action=WIKI_SYNC_COMPLETED_ACTION,
        actor_role=context.role.value,
        actor_id=context.actor_id,
        request_id=context.request_id,
        idempotency_key=context.idempotency_key,
        created_at=promoted_candidate.approved_at,
        notes="Candidate promotion has been synchronized into the formal wiki.",
    )
    return ReviewActionResponse(
        candidate=candidate_to_payload(promoted_candidate),
        patch=patch_draft.patch_payload,
        wiki_page={
            "page_id": patch_draft.target_page_id,
            "path": _as_data_relative_path(settings, patch_draft.target_path),
            "operation": patch_draft.operation,
            "updated_at": promoted_candidate.approved_at.isoformat().replace("+00:00", "Z"),
        },
    )


def merge_review_candidate(
    settings: Settings,
    *,
    candidate_id: str,
    payload: ReviewMergeRequest,
    context: RequestContext,
) -> ReviewActionResponse:
    if context.idempotency_key is None or not context.idempotency_key.strip():
        raise ReviewStateError("Idempotency-Key is required for candidate merge")

    source_candidate = _load_visible_candidate(settings, candidate_id=candidate_id, context=context)
    _assert_action_allowed(source_candidate, context=context, action="merge")
    target_candidate = _load_visible_candidate(
        settings,
        candidate_id=payload.target_candidate_id,
        context=context,
    )
    merged_candidate = merge_candidate(
        settings,
        candidate_id,
        target_candidate_id=target_candidate.candidate_id,
        actor_role=context.role,
        actor_id=context.actor_id,
        request_id=context.request_id,
        idempotency_key=context.idempotency_key,
        notes=payload.merge_notes,
    )
    refreshed_target = get_candidate(settings, target_candidate.candidate_id)
    return ReviewActionResponse(
        candidate=candidate_to_payload(merged_candidate),
        target_candidate=candidate_to_payload(refreshed_target),
    )


def drop_review_candidate(
    settings: Settings,
    *,
    candidate_id: str,
    payload: ReviewDropRequest,
    context: RequestContext,
) -> ReviewActionResponse:
    if context.idempotency_key is None or not context.idempotency_key.strip():
        raise ReviewStateError("Idempotency-Key is required for candidate drop")

    candidate = _load_visible_candidate(settings, candidate_id=candidate_id, context=context)
    _assert_action_allowed(candidate, context=context, action="drop")
    notes = payload.drop_notes or f"Drop reason: {payload.reason}"
    dropped_candidate = drop_candidate(
        settings,
        candidate_id,
        actor_role=context.role,
        actor_id=context.actor_id,
        request_id=context.request_id,
        idempotency_key=context.idempotency_key,
        notes=notes,
    )
    return ReviewActionResponse(
        candidate=candidate_to_payload(dropped_candidate),
    )


def candidate_to_payload(candidate: CandidateItem) -> dict[str, object]:
    payload = candidate.model_dump(mode="json", exclude_none=True)
    payload["review_domain"] = _candidate_review_domain(candidate).value
    return payload


def _load_visible_candidate(
    settings: Settings,
    *,
    candidate_id: str,
    context: RequestContext,
) -> CandidateItem:
    _assert_review_role(context)
    candidate = get_candidate(settings, candidate_id)
    if candidate.course_id != context.course_id or candidate.class_id != context.class_id:
        raise ForbiddenReviewScopeError("Candidate is outside the current course/class scope.")
    if not _is_candidate_visible(candidate, context=context):
        raise ForbiddenReviewScopeError("Candidate is outside the current role boundary.")
    return candidate


def _assert_review_role(context: RequestContext) -> None:
    if context.role not in REVIEWABLE_ROLES:
        raise ForbiddenReviewScopeError("This role cannot access the review workflow.")
    expected_domain = {
        ActorRole.INSTRUCTOR: RequestDomain.ACADEMIC,
        ActorRole.OPERATOR: RequestDomain.OPERATIONS,
        ActorRole.VALIDATOR: RequestDomain.REVIEW,
        ActorRole.SYSTEM: RequestDomain.REVIEW,
    }[context.role]
    if context.domain is not expected_domain:
        raise ForbiddenReviewScopeError(
            f"This role must use the {expected_domain.value} domain for review workflows."
        )


def _is_candidate_visible(candidate: CandidateItem, *, context: RequestContext) -> bool:
    candidate_domain = _candidate_review_domain(candidate)
    if context.role is ActorRole.SYSTEM:
        return True
    if context.role is ActorRole.VALIDATOR:
        return True
    if context.role is ActorRole.INSTRUCTOR:
        return candidate_domain is RequestDomain.ACADEMIC
    if context.role is ActorRole.OPERATOR:
        return candidate_domain is RequestDomain.OPERATIONS
    return False


def _available_actions(candidate: CandidateItem, *, context: RequestContext) -> list[str]:
    if context.role not in REVIEWABLE_ROLES:
        return []
    if not _is_candidate_visible(candidate, context=context):
        return []
    if candidate.status is not CandidateStatus.OPEN:
        return []
    if not _can_finalize_candidate(candidate, context=context):
        return ["patch_preview"]
    return ["patch_preview", "approve", "merge", "drop"]


def _can_finalize_candidate(candidate: CandidateItem, *, context: RequestContext) -> bool:
    if context.role is ActorRole.OPERATOR:
        return False
    if (
        context.role is ActorRole.INSTRUCTOR
        and _candidate_review_domain(candidate) is RequestDomain.OPERATIONS
    ):
        return False
    return True


def _assert_action_allowed(
    candidate: CandidateItem,
    *,
    context: RequestContext,
    action: str,
) -> None:
    if not _can_finalize_candidate(candidate, context=context):
        raise ForbiddenReviewScopeError(
            f"This role cannot {action} candidates in the current scope."
        )


def _candidate_review_domain(candidate: CandidateItem) -> RequestDomain:
    if candidate.kind in ACADEMIC_REVIEW_KINDS:
        return RequestDomain.ACADEMIC
    return RequestDomain.OPERATIONS


def _build_patch_draft(
    settings: Settings,
    *,
    candidate: CandidateItem,
    context: RequestContext,
    target_page_id: str | None,
    target_path: str | None,
    notes: str | None,
    approval_status: str,
    approved_by: str | None,
    approved_at: datetime | None,
) -> WikiPatchDraft:
    target_page_id = target_page_id or candidate.related_page_id
    if target_page_id is None:
        raise ReviewStateError("candidate approval requires a target_page_id")

    domain_name = WIKI_DOMAIN_BY_KIND[candidate.kind]
    existing_page = get_wiki_page(settings, target_page_id)
    resolved_path = _resolve_target_path(
        settings,
        domain_name=domain_name,
        target_page_id=target_page_id,
        target_path=target_path,
        existing_page_path=Path(existing_page.path) if existing_page is not None else None,
    )
    before_markdown = resolved_path.read_text(encoding="utf-8") if resolved_path.exists() else None
    if before_markdown is None and existing_page is not None:
        before_markdown = Path(existing_page.path).read_text(encoding="utf-8")
        resolved_path = Path(existing_page.path)

    page_title = existing_page.title if existing_page is not None else _derive_page_title(candidate)
    summary = existing_page.summary if existing_page is not None else candidate.summary
    source_ids = _merge_unique_strings(
        existing_page.source_refs if existing_page is not None else [],
        [source_ref.source_id for source_ref in candidate.source_refs],
    )
    candidate_refs = _merge_unique_strings(
        existing_page.candidate_refs if existing_page is not None else [],
        [candidate.candidate_id],
    )
    source_contents = _load_source_contents(settings, candidate)
    body_markdown, change_plan = _build_body_markdown(
        candidate=candidate,
        page_title=page_title,
        existing_body=existing_page.body_markdown if existing_page is not None else None,
        source_contents=source_contents,
    )
    effective_updated_at = approved_at or datetime.now(UTC)
    wiki_metadata = {
        "page_id": target_page_id,
        "domain": domain_name,
        "title": page_title,
        "course_id": candidate.course_id,
        "class_scope": candidate.class_id,
        "updated_at": effective_updated_at.isoformat().replace("+00:00", "Z"),
        "source_refs": source_ids,
        "candidate_refs": candidate_refs,
        "summary": summary,
    }
    after_markdown = build_frontmatter_document(wiki_metadata, body_markdown)
    patch_payload = {
        "target_page_id": target_page_id,
        "target_path": _as_data_relative_path(settings, resolved_path),
        "operation": "update" if resolved_path.exists() else "create",
        "title": page_title,
        "summary": summary,
        "domain": domain_name,
        "course_id": candidate.course_id,
        "class_id": candidate.class_id,
        "actor_role": context.role.value,
        "change_plan": change_plan,
        "source_refs": [
            source_ref.model_dump(mode="json", exclude_none=True)
            for source_ref in candidate.source_refs
        ],
        "candidate_refs": candidate_refs,
        "created_at": effective_updated_at.isoformat().replace("+00:00", "Z"),
        "approval_status": approval_status,
    }
    if approved_by is not None:
        patch_payload["approved_by"] = approved_by
    if approved_at is not None:
        patch_payload["approved_at"] = approved_at.isoformat().replace("+00:00", "Z")

    return WikiPatchDraft(
        patch_payload=patch_payload,
        before_markdown=before_markdown,
        after_markdown=after_markdown,
        target_page_id=target_page_id,
        target_path=resolved_path,
        operation=patch_payload["operation"],
    )


def _resolve_target_path(
    settings: Settings,
    *,
    domain_name: str,
    target_page_id: str,
    target_path: str | None,
    existing_page_path: Path | None,
) -> Path:
    slug_prefix = f"page-{domain_name}-"
    if not target_page_id.startswith(slug_prefix) or target_page_id == slug_prefix:
        raise ReviewStateError(
            f"target_page_id must match the page-{domain_name}-<slug> contract"
        )

    if existing_page_path is not None:
        canonical_path = existing_page_path.resolve()
    else:
        slug = target_page_id[len(slug_prefix) :]
        canonical_path = (settings.data_root / "wiki" / domain_name / f"{slug}.md").resolve()

    if target_path:
        candidate_path = Path(target_path)
        if candidate_path.parts[:1] == ("data",):
            candidate_path = settings.data_root / Path(*candidate_path.parts[1:])
        elif not candidate_path.is_absolute():
            candidate_path = settings.data_root / candidate_path
        resolved_path = candidate_path.resolve()
        if resolved_path != canonical_path:
            raise ReviewStateError(
                "target_path must match the canonical wiki path for target_page_id"
            )
    else:
        resolved_path = canonical_path

    wiki_root = (settings.data_root / "wiki").resolve()
    try:
        resolved_path.relative_to(wiki_root)
    except ValueError as exc:
        raise ReviewStateError("target_path escapes the configured wiki root") from exc
    return resolved_path


def _load_source_contents(settings: Settings, candidate: CandidateItem) -> list[str]:
    contents: list[str] = []
    for source_ref in candidate.source_refs:
        try:
            source_record = get_source(settings, source_ref.source_id)
        except SourceNotFoundError:
            continue
        source_path = resolve_source_path(settings, source_record.origin_path)
        if not source_path.exists():
            continue
        contents.append(source_path.read_text(encoding="utf-8"))
    return contents


def _build_body_markdown(
    *,
    candidate: CandidateItem,
    page_title: str,
    existing_body: str | None,
    source_contents: list[str],
) -> tuple[str, list[str]]:
    if candidate.kind is CandidateKind.FAQ:
        return _build_faq_body(
            candidate=candidate,
            page_title=page_title,
            existing_body=existing_body,
            source_contents=source_contents,
        )
    return _build_generic_body(
        candidate=candidate,
        page_title=page_title,
        existing_body=existing_body,
    )


def _build_faq_body(
    *,
    candidate: CandidateItem,
    page_title: str,
    existing_body: str | None,
    source_contents: list[str],
) -> tuple[str, list[str]]:
    combined_sentences = _extract_sentences(
        "\n\n".join(filter(None, [existing_body, *source_contents]))
    )
    submit_sentence = _pick_sentence(combined_sentences, keywords=("submit", "lms"))
    deadline_sentence = _pick_sentence(combined_sentences, keywords=("due", "deadline"))
    late_sentence = _pick_sentence(combined_sentences, keywords=("late", "accommodation"))

    change_plan = [
        "Review and apply the structured FAQ candidate to the formal wiki page.",
    ]
    lines = [f"# {page_title}"]

    if submit_sentence:
        lines.extend(["", submit_sentence])
        change_plan.append("Keep LMS submission instructions at the top of the page.")
    else:
        lines.extend(["", candidate.summary])

    if deadline_sentence:
        lines.extend(["", "## Deadline", "", deadline_sentence])
        change_plan.append("Clarify the deadline in a dedicated section.")

    if late_sentence:
        lines.extend(["", "## Late policy", "", late_sentence])
        change_plan.append("Document the late policy for quick review.")

    body_markdown = "\n".join(lines).strip() + "\n"
    return body_markdown, change_plan


def _build_generic_body(
    *,
    candidate: CandidateItem,
    page_title: str,
    existing_body: str | None,
) -> tuple[str, list[str]]:
    if existing_body:
        return existing_body.strip() + "\n", [
            "Preserve the existing reviewed page body while linking the approved candidate.",
        ]

    lines = [
        f"# {page_title}",
        "",
        candidate.summary,
    ]
    if candidate.kind is CandidateKind.MISCONCEPTION:
        lines.extend(
            [
                "",
                "## What students are mixing up",
                "",
                candidate.summary,
            ]
        )
    return "\n".join(lines).strip() + "\n", [
        "Create a new reviewed wiki page from the candidate summary.",
    ]


def _pick_sentence(sentences: list[str], *, keywords: tuple[str, ...]) -> str | None:
    for sentence in sentences:
        lowered = sentence.lower()
        if any(keyword in lowered for keyword in keywords):
            return sentence
    return None


def _extract_sentences(contents: str) -> list[str]:
    normalized = contents.replace("\r\n", "\n")
    chunks = [chunk.strip() for chunk in normalized.splitlines() if chunk.strip()]
    sentences: list[str] = []
    for chunk in chunks:
        if chunk.startswith("#"):
            continue
        if chunk.startswith("---"):
            continue
        sentences.append(chunk)
    return _dedupe_preserve_order(sentences)


def _derive_page_title(candidate: CandidateItem) -> str:
    if candidate.kind is CandidateKind.FAQ and "homework" in candidate.title.lower():
        return "Homework Submission"
    return candidate.title


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item in seen:
            continue
        deduped.append(item)
        seen.add(item)
    return deduped


def _merge_unique_strings(base: list[str], extra: list[str]) -> list[str]:
    merged = list(base)
    seen = set(base)
    for item in extra:
        if item in seen:
            continue
        merged.append(item)
        seen.add(item)
    return merged


def _write_wiki_page(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def _as_data_relative_path(settings: Settings, path: Path) -> str:
    resolved_path = path.resolve()
    data_root = settings.data_root.resolve()
    relative_path = resolved_path.relative_to(data_root)
    return (Path("data") / relative_path).as_posix()
