from __future__ import annotations

import re
from enum import StrEnum

IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$")
COURSE_ID_PATTERN = re.compile(r"^course-[a-z0-9][a-z0-9-]*[a-z0-9]$")
CLASS_ID_PATTERN = re.compile(r"^class-[a-z0-9][a-z0-9-]*[a-z0-9]$")
ACTOR_ID_PATTERNS = {
    "student": re.compile(r"^stu-[a-z0-9][a-z0-9-]*[a-z0-9]$"),
    "instructor": re.compile(r"^ins-[a-z0-9][a-z0-9-]*[a-z0-9]$"),
    "operator": re.compile(r"^ops-[a-z0-9][a-z0-9-]*[a-z0-9]$"),
    "validator": re.compile(r"^val-[a-z0-9][a-z0-9-]*[a-z0-9]$"),
    "system": re.compile(
        r"^(system(?:-[a-z0-9][a-z0-9-]*[a-z0-9])?|sys-[a-z0-9][a-z0-9-]*[a-z0-9])$"
    ),
}


class ActorRole(StrEnum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"
    OPERATOR = "operator"
    VALIDATOR = "validator"
    SYSTEM = "system"


class RequestDomain(StrEnum):
    ACADEMIC = "academic"
    OPERATIONS = "operations"
    REVIEW = "review"


class SourceType(StrEnum):
    LECTURE_NOTE = "lecture_note"
    LECTURE_TRANSCRIPT = "lecture_transcript"
    STUDENT_QUESTION = "student_question"
    ASSIGNMENT_FEEDBACK = "assignment_feedback"
    ANNOUNCEMENT = "announcement"
    OPERATIONS_NOTE = "operations_note"
    COUNSELING_NOTE = "counseling_note"


ACADEMIC_SOURCE_TYPES = frozenset(
    {
        SourceType.LECTURE_NOTE,
        SourceType.LECTURE_TRANSCRIPT,
        SourceType.STUDENT_QUESTION,
        SourceType.ASSIGNMENT_FEEDBACK,
    }
)

OPERATIONS_SOURCE_TYPES = frozenset(
    {
        SourceType.OPERATIONS_NOTE,
        SourceType.COUNSELING_NOTE,
    }
)

FLEXIBLE_DOMAIN_SOURCE_TYPES = frozenset({SourceType.ANNOUNCEMENT})


def default_domain_for_role(role: ActorRole) -> RequestDomain | None:
    if role in {ActorRole.STUDENT, ActorRole.INSTRUCTOR}:
        return RequestDomain.ACADEMIC
    if role is ActorRole.OPERATOR:
        return RequestDomain.OPERATIONS
    if role is ActorRole.VALIDATOR:
        return RequestDomain.REVIEW
    return None


def allowed_domains_for_source_type(source_type: SourceType) -> frozenset[RequestDomain]:
    if source_type in FLEXIBLE_DOMAIN_SOURCE_TYPES:
        return frozenset({RequestDomain.ACADEMIC, RequestDomain.OPERATIONS})
    if source_type in ACADEMIC_SOURCE_TYPES:
        return frozenset({RequestDomain.ACADEMIC})
    return frozenset({RequestDomain.OPERATIONS})


def allowed_domains_for_role(actor_role: ActorRole) -> frozenset[RequestDomain]:
    if actor_role is ActorRole.STUDENT:
        return frozenset({RequestDomain.ACADEMIC})
    if actor_role is ActorRole.INSTRUCTOR:
        return frozenset({RequestDomain.ACADEMIC})
    if actor_role is ActorRole.OPERATOR:
        return frozenset({RequestDomain.OPERATIONS})
    if actor_role in {ActorRole.VALIDATOR, ActorRole.SYSTEM}:
        return frozenset(
            {
                RequestDomain.ACADEMIC,
                RequestDomain.OPERATIONS,
                RequestDomain.REVIEW,
            }
        )
    return frozenset()


def is_request_domain_allowed_for_role(
    actor_role: ActorRole,
    requested_domain: RequestDomain | None,
) -> bool:
    if requested_domain is None:
        return True
    if actor_role is ActorRole.VALIDATOR and requested_domain is RequestDomain.REVIEW:
        return True
    return requested_domain in allowed_domains_for_role(actor_role)


def is_source_type_allowed_for_role(
    source_type: SourceType,
    *,
    actor_role: ActorRole,
    requested_domain: RequestDomain | None,
) -> bool:
    domain_candidates = allowed_domains_for_source_type(source_type).intersection(
        allowed_domains_for_role(actor_role)
    )
    if not domain_candidates:
        return False
    if actor_role in {ActorRole.VALIDATOR, ActorRole.SYSTEM} and requested_domain in {
        None,
        RequestDomain.REVIEW,
    }:
        return True
    if requested_domain is None:
        return True
    return requested_domain in domain_candidates


def resolve_source_domain(
    source_type: SourceType,
    *,
    actor_role: ActorRole,
    requested_domain: RequestDomain | None,
) -> RequestDomain:
    domain_candidates = allowed_domains_for_source_type(source_type).intersection(
        allowed_domains_for_role(actor_role)
    )
    if not domain_candidates:
        raise ValueError("source_type is not allowed for this role")
    if requested_domain is not None:
        if requested_domain not in domain_candidates:
            raise ValueError("requested domain is not allowed for this source_type and role")
        return requested_domain
    if len(domain_candidates) == 1:
        return next(iter(domain_candidates))
    raise ValueError("domain is required for this source_type and role")


def validate_actor_id(actor_id: str, *, actor_role: ActorRole | None = None) -> str:
    normalized = _validate_identifier(actor_id, field_name="actor_id", pattern=IDENTIFIER_PATTERN)
    if actor_role is None:
        return normalized
    role_pattern = ACTOR_ID_PATTERNS[actor_role.value]
    if not role_pattern.fullmatch(normalized):
        raise ValueError("actor_id does not match the declared Knowloop role")
    return normalized


def validate_course_id(course_id: str) -> str:
    return _validate_identifier(course_id, field_name="course_id", pattern=COURSE_ID_PATTERN)


def validate_class_id(class_id: str) -> str:
    return _validate_identifier(class_id, field_name="class_id", pattern=CLASS_ID_PATTERN)


def _validate_identifier(value: str, *, field_name: str, pattern: re.Pattern[str]) -> str:
    normalized = value.strip()
    if "/" in normalized or "\\" in normalized:
        raise ValueError(f"{field_name} must not contain path separators")
    if not pattern.fullmatch(normalized):
        raise ValueError(f"{field_name} does not match the Knowloop ID contract")
    return normalized
