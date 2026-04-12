from __future__ import annotations

from enum import StrEnum

from knowloop_api.core.contracts import ActorRole, RequestDomain


class ResponseMode(StrEnum):
    DEFAULT = "default"
    CONCISE = "concise"
    TEACHING = "teaching"
    REVIEW = "review"


class AnswerBasisLabel(StrEnum):
    FORMAL_WIKI = "formal_wiki"
    LEARNING_CONTEXT = "learning_context"
    RAW_SOURCE_FALLBACK = "raw_source_fallback"
    SESSION_CONTEXT = "session_context"


QUERY_RESPONSE_MODES = frozenset(item.value for item in ResponseMode)
QUERY_ANSWER_BASIS = frozenset(item.value for item in AnswerBasisLabel)
QUERY_ANSWER_BASIS_ORDER = (
    AnswerBasisLabel.FORMAL_WIKI.value,
    AnswerBasisLabel.SESSION_CONTEXT.value,
    AnswerBasisLabel.LEARNING_CONTEXT.value,
    AnswerBasisLabel.RAW_SOURCE_FALLBACK.value,
)

PUBLIC_QUERY_ROUTE_DOMAINS_V1 = {
    ActorRole.STUDENT.value: RequestDomain.ACADEMIC.value,
    ActorRole.INSTRUCTOR.value: RequestDomain.ACADEMIC.value,
    ActorRole.OPERATOR.value: RequestDomain.OPERATIONS.value,
    ActorRole.VALIDATOR.value: RequestDomain.REVIEW.value,
}
