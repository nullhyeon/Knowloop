from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole, RequestDomain
from knowloop_api.core.frontmatter import parse_frontmatter_document
from knowloop_api.core.pagination import collect_descending_page

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


class WikiPageAmbiguityError(ValueError):
    """Raised when a wiki page ID resolves to multiple pages without scope."""


ACADEMIC_WIKI_DOMAINS = frozenset({"concepts", "faq", "misconceptions", "courses"})
OPERATIONS_WIKI_DOMAINS = frozenset({"operations"})
ALL_WIKI_DOMAINS = ACADEMIC_WIKI_DOMAINS.union(OPERATIONS_WIKI_DOMAINS)
PAGE_ID_SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


def build_wiki_page_path(
    settings: Settings,
    *,
    domain: str,
    class_scope: str,
    page_id: str,
) -> Path:
    slug_prefix = f"page-{domain}-"
    if not page_id.startswith(slug_prefix) or page_id == slug_prefix:
        raise ValueError(f"page_id must match the page-{domain}-<slug> contract")
    slug = page_id[len(slug_prefix) :]
    if not PAGE_ID_SLUG_PATTERN.fullmatch(slug):
        raise ValueError("page_id slug must contain only lowercase letters, digits, and hyphens")
    return settings.data_root / "wiki" / domain / class_scope / f"{slug}.md"


def get_wiki_page(
    settings: Settings,
    page_id: str,
    *,
    course_id: str | None = None,
    class_id: str | None = None,
) -> WikiPage | None:
    matches = [
        page
        for page in find_wiki_pages_by_id(settings, page_id)
        if (course_id is None or page.course_id == course_id)
        and (class_id is None or page.class_scope == class_id)
    ]
    if not matches:
        return None
    if course_id is None and class_id is None and len(matches) > 1:
        raise WikiPageAmbiguityError(
            f"wiki page id resolves to multiple scoped pages: {page_id}"
        )
    return matches[0]


def find_wiki_pages_by_id(settings: Settings, page_id: str) -> list[WikiPage]:
    return [page for page in list_wiki_pages(settings) if page.page_id == page_id]


def list_wiki_pages(settings: Settings) -> list[WikiPage]:
    wiki_root = settings.data_root / "wiki"
    if not wiki_root.exists():
        return []

    return list(
        _iter_wiki_pages_from_paths(
            settings,
            sorted(wiki_root.glob("**/*.md")),
            include_body=True,
        )
    )


def _collect_visible_wiki_pages(
    settings: Settings,
    *,
    role: ActorRole,
    course_id: str,
    class_id: str,
    requested_domain: RequestDomain | None,
) -> list[WikiPage]:
    return list(
        _iter_visible_wiki_pages(
            settings,
            role=role,
            course_id=course_id,
            class_id=class_id,
            requested_domain=requested_domain,
            include_body=True,
        )
    )


def _iter_visible_wiki_pages(
    settings: Settings,
    *,
    role: ActorRole,
    course_id: str,
    class_id: str,
    requested_domain: RequestDomain | None,
    include_body: bool,
) -> Iterator[WikiPage]:
    allowed_domains = _visible_wiki_domains(role, requested_domain=requested_domain)
    for page in _iter_wiki_pages_from_paths(
        settings,
        _iter_visible_wiki_paths(settings, allowed_domains=allowed_domains, class_id=class_id),
        include_body=include_body,
    ):
        if (
            page.course_id == course_id
            and page.class_scope == class_id
            and page.domain in allowed_domains
        ):
            yield page


def _iter_visible_wiki_paths(
    settings: Settings,
    *,
    allowed_domains: set[str],
    class_id: str,
) -> Iterator[Path]:
    wiki_root = settings.data_root / "wiki"
    for domain in sorted(allowed_domains):
        scoped_root = wiki_root / domain / class_id
        if not scoped_root.is_dir():
            continue
        yield from sorted(scoped_root.glob("*.md"))


def _iter_wiki_pages_from_paths(
    settings: Settings,
    paths: Iterable[Path],
    *,
    include_body: bool,
) -> Iterator[WikiPage]:
    for path in paths:
        if path.name.startswith("."):
            continue
        try:
            page = _load_wiki_page(path) if include_body else _load_wiki_page_metadata(path)
            if not _is_canonical_wiki_page_path(settings, page=page, path=path):
                continue
        except (KeyError, OSError, ValueError):
            continue
        yield page


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
    normalized_query = (query or "").strip()
    if normalized_query:
        visible_pages = _collect_visible_wiki_pages(
            settings,
            role=role,
            course_id=course_id,
            class_id=class_id,
            requested_domain=requested_domain,
        )
        visible_pages = [match.page for match in _rank_wiki_pages(visible_pages, query=query)]
        total = len(visible_pages)
        return visible_pages[offset : offset + limit], total

    return collect_descending_page(
        _iter_visible_wiki_pages(
            settings,
            role=role,
            course_id=course_id,
            class_id=class_id,
            requested_domain=requested_domain,
            include_body=False,
        ),
        key=lambda page: (page.updated_at, page.page_id),
        limit=limit,
        offset=offset,
    )


def get_visible_wiki_page(
    settings: Settings,
    *,
    page_id: str,
    role: ActorRole,
    course_id: str,
    class_id: str,
    requested_domain: RequestDomain | None,
) -> WikiPage:
    page = get_wiki_page(
        settings,
        page_id,
        course_id=course_id,
        class_id=class_id,
    )
    if page is None:
        raise WikiPageNotFoundError(f"wiki page was not found: {page_id}")
    if page.domain not in _visible_wiki_domains(role, requested_domain=requested_domain):
        raise ForbiddenWikiScopeError("Wiki page is outside the current role boundary.")
    return page


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
    return _build_wiki_page_from_metadata(metadata, body=body, path=path)


def _load_wiki_page_metadata(path: Path) -> WikiPage:
    metadata = _read_frontmatter_metadata_only(path)
    return _build_wiki_page_from_metadata(metadata, body="", path=path)


def _build_wiki_page_from_metadata(
    metadata: dict[str, object],
    *,
    body: str,
    path: Path,
) -> WikiPage:
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


def _read_frontmatter_metadata_only(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        first_line = handle.readline()
        if first_line.strip() != "---":
            return {}
        frontmatter_lines: list[str] = ["---"]
        for line in handle:
            frontmatter_lines.append(line.rstrip("\n"))
            if line.strip() == "---":
                break
        else:
            return {}
    metadata, _body = parse_frontmatter_document("\n".join(frontmatter_lines) + "\n")
    return metadata


def load_wiki_page_from_path(path: Path) -> WikiPage:
    return _load_wiki_page(path)


def load_wiki_page_metadata_from_path(path: Path) -> WikiPage:
    return _load_wiki_page_metadata(path)


def _is_canonical_wiki_page_path(
    settings: Settings,
    *,
    page: WikiPage,
    path: Path,
) -> bool:
    canonical_path = build_wiki_page_path(
        settings,
        domain=page.domain,
        class_scope=page.class_scope,
        page_id=page.page_id,
    ).resolve()
    return canonical_path == path.resolve()


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
