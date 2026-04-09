from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import RequestDomain
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
    course_id: str,
    class_id: str,
    requested_domain: RequestDomain | None,
    message: str,
    limit: int = 5,
) -> list[WikiPageMatch]:
    requested_tokens = _tokenize(message)
    allowed_domains = _allowed_wiki_domains(requested_domain)
    matches: list[WikiPageMatch] = []
    for page in list_wiki_pages(settings):
        if page.course_id != course_id or page.class_scope != class_id:
            continue
        if page.domain not in allowed_domains:
            continue
        score = _score_page(page, requested_tokens=requested_tokens, message=message.lower())
        if score <= 0:
            continue
        matches.append(WikiPageMatch(page=page, score=score))

    return sorted(
        matches,
        key=lambda match: (match.score, match.page.updated_at, match.page.page_id),
        reverse=True,
    )[:limit]


def _allowed_wiki_domains(requested_domain: RequestDomain | None) -> set[str]:
    if requested_domain is RequestDomain.OPERATIONS:
        return {"operations"}
    if requested_domain is RequestDomain.REVIEW:
        return {"concepts", "faq", "misconceptions", "operations", "courses"}
    return {"concepts", "faq", "misconceptions", "courses"}


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


def _score_page(page: WikiPage, *, requested_tokens: set[str], message: str) -> int:
    haystack = " ".join([page.title, page.summary, page.body_markdown]).lower()
    haystack_tokens = _tokenize(haystack)
    token_matches = sum(3 for token in requested_tokens if token in haystack_tokens)
    phrase_bonus = 0
    if "chain rule" in message and "chain rule" in haystack:
        phrase_bonus += 6
    if "product rule" in message and "product rule" in haystack:
        phrase_bonus += 6
    if "homework" in message and "homework" in haystack:
        phrase_bonus += 4
    if "deadline" in message and "deadline" in haystack:
        phrase_bonus += 4
    if "refund" in message and "refund" in haystack:
        phrase_bonus += 6
    return token_matches + phrase_bonus


def _tokenize(value: str) -> set[str]:
    return {
        token
        for token in TOKEN_PATTERN.findall(value.lower())
        if len(token) >= 3 and token not in STOPWORDS
    }
