from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole, RequestDomain
from knowloop_api.core.frontmatter import parse_frontmatter_document

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "also",
    "always",
    "among",
    "about",
    "again",
    "around",
    "because",
    "being",
    "between",
    "both",
    "can",
    "class",
    "could",
    "does",
    "doing",
    "done",
    "each",
    "every",
    "from",
    "have",
    "into",
    "just",
    "made",
    "make",
    "more",
    "most",
    "much",
    "must",
    "only",
    "other",
    "over",
    "same",
    "should",
    "some",
    "still",
    "such",
    "tell",
    "than",
    "that",
    "them",
    "then",
    "they",
    "this",
    "through",
    "used",
    "using",
    "very",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "without",
    "would",
    "your",
    "the",
    "and",
    "for",
    "you",
    "our",
    "not",
    "test",
}


class WikiPage(BaseModel):
    page_id: str
    domain: str
    title: str
    course_id: str
    class_scope: str
    updated_at: datetime
    source_refs: list[str]
    candidate_refs: list[str]
    summary: str
    body_markdown: str
    path: str


@dataclass(slots=True)
class WikiPageMatch:
    page: WikiPage
    score: int


class WikiPageNotFoundError(FileNotFoundError):
    """Raised when a wiki page cannot be found."""


class ForbiddenWikiScopeError(PermissionError):
    """Raised when a caller crosses the wiki visibility boundary."""


ACADEMIC_WIKI_DOMAINS = frozenset({"concepts", "faq", "misconceptions", "courses"})
OPERATIONS_WIKI_DOMAINS = frozenset({"operations"})
ALL_WIKI_DOMAINS = ACADEMIC_WIKI_DOMAINS.union(OPERATIONS_WIKI_DOMAINS)


def get_wiki_page(settings: Settings, page_id: str) -> WikiPage | None:
    for page in list_wiki_pages(settings):
        if page.page_id == page_id:
            return page
    return None


def list_wiki_pages(settings: Settings) -> list[WikiPage]:
    wiki_root = settings.data_root / "wiki"
    if not wiki_root.exists():
        return []

    pages: list[WikiPage] = []
    for path in sorted(wiki_root.glob("**/*.md")):
        if path.name.startswith("."):
            continue
        pages.append(_load_wiki_page(path))
    return pages


def search_wiki_pages(
    settings: Settings,
    *,
    role: ActorRole,
    course_id: str,
    class_id: str,
    requested_domain: RequestDomain | None,
    message: str,
    limit: int = 5,
) -> list[WikiPageMatch]:
    visible_pages = _collect_visible_wiki_pages(
        settings,
        role=role,
        course_id=course_id,
        class_id=class_id,
        requested_domain=requested_domain,
    )
    return _rank_wiki_pages(visible_pages, query=message)[:limit]


def list_visible_wiki_pages(
    settings: Settings,
    *,
    role: ActorRole,
    course_id: str,
    class_id: str,
    requested_domain: RequestDomain | None,
    query: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[WikiPage], int]:
    visible_pages = _collect_visible_wiki_pages(
        settings,
        role=role,
        course_id=course_id,
        class_id=class_id,
        requested_domain=requested_domain,
    )

    normalized_query = (query or "").strip()
    if normalized_query:
        visible_pages = [match.page for match in _rank_wiki_pages(visible_pages, query=query)]
    else:
        visible_pages = sorted(
            visible_pages,
            key=lambda page: (page.updated_at, page.page_id),
            reverse=True,
        )

    total = len(visible_pages)
    return visible_pages[offset : offset + limit], total


def get_visible_wiki_page(
    settings: Settings,
    *,
    page_id: str,
    role: ActorRole,
    course_id: str,
    class_id: str,
    requested_domain: RequestDomain | None,
) -> WikiPage:
    page = get_wiki_page(settings, page_id)
    if page is None:
        raise WikiPageNotFoundError(f"wiki page was not found: {page_id}")
    if page.course_id != course_id or page.class_scope != class_id:
        raise ForbiddenWikiScopeError("Wiki page is outside the current course/class scope.")
    if page.domain not in _visible_wiki_domains(role, requested_domain=requested_domain):
        raise ForbiddenWikiScopeError("Wiki page is outside the current role boundary.")
    return page


def _collect_visible_wiki_pages(
    settings: Settings,
    *,
    role: ActorRole,
    course_id: str,
    class_id: str,
    requested_domain: RequestDomain | None,
) -> list[WikiPage]:
    allowed_domains = _visible_wiki_domains(role, requested_domain=requested_domain)
    return [
        page
        for page in list_wiki_pages(settings)
        if page.course_id == course_id
        and page.class_scope == class_id
        and page.domain in allowed_domains
    ]


def _visible_wiki_domains(
    role: ActorRole,
    *,
    requested_domain: RequestDomain | None,
) -> set[str]:
    if role in {ActorRole.STUDENT, ActorRole.INSTRUCTOR}:
        return set(ACADEMIC_WIKI_DOMAINS)
    if role is ActorRole.OPERATOR:
        return set(OPERATIONS_WIKI_DOMAINS)
    if role in {ActorRole.VALIDATOR, ActorRole.SYSTEM}:
        if requested_domain in {None, RequestDomain.REVIEW}:
            return set(ALL_WIKI_DOMAINS)
        if requested_domain is RequestDomain.ACADEMIC:
            return set(ACADEMIC_WIKI_DOMAINS)
        if requested_domain is RequestDomain.OPERATIONS:
            return set(OPERATIONS_WIKI_DOMAINS)
    raise ForbiddenWikiScopeError("This role cannot access the wiki browser.")


def _rank_wiki_pages(pages: list[WikiPage], *, query: str) -> list[WikiPageMatch]:
    normalized_query = query.strip().lower()
    requested_tokens = _tokenize(normalized_query)
    matches = [
        WikiPageMatch(
            page=page,
            score=_score_page(
                page,
                requested_tokens=requested_tokens,
                normalized_query=normalized_query,
            ),
        )
        for page in pages
    ]
    return sorted(
        (match for match in matches if match.score > 0),
        key=lambda match: (match.score, match.page.updated_at, match.page.page_id),
        reverse=True,
    )


def _load_wiki_page(path: Path) -> WikiPage:
    metadata, body = parse_frontmatter_document(path.read_text(encoding="utf-8"))
    return WikiPage(
        page_id=str(metadata["page_id"]),
        domain=str(metadata["domain"]),
        title=str(metadata["title"]),
        course_id=str(metadata["course_id"]),
        class_scope=str(metadata["class_scope"]),
        updated_at=datetime.fromisoformat(str(metadata["updated_at"]).replace("Z", "+00:00")),
        source_refs=[str(item) for item in metadata.get("source_refs", [])],
        candidate_refs=[str(item) for item in metadata.get("candidate_refs", [])],
        summary=str(metadata["summary"]),
        body_markdown=body,
        path=path.as_posix(),
    )


def _score_page(
    page: WikiPage,
    *,
    requested_tokens: set[str],
    normalized_query: str,
) -> int:
    if not requested_tokens and not normalized_query:
        return 0

    title = page.title.lower()
    summary = page.summary.lower()
    body = page.body_markdown.lower()
    title_tokens = _tokenize(title)
    summary_tokens = _tokenize(summary)
    body_tokens = _tokenize(body)

    token_score = 0
    for token in requested_tokens:
        if token in title_tokens:
            token_score += 8
        if token in summary_tokens:
            token_score += 5
        if token in body_tokens:
            token_score += 2

    phrase_bonus = 0
    if normalized_query:
        if title == normalized_query:
            phrase_bonus += 12
        elif normalized_query in title:
            phrase_bonus += 8
        if normalized_query in summary:
            phrase_bonus += 5
        if normalized_query in body:
            phrase_bonus += 3

    return token_score + phrase_bonus


def _tokenize(value: str) -> set[str]:
    return {
        token
        for token in TOKEN_PATTERN.findall(value.lower())
        if len(token) >= 3 and token not in STOPWORDS
    }
