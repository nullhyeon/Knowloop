from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Header
from pydantic import BaseModel

from knowloop_api.api.errors import ApiError
from knowloop_api.core.contracts import (
    ActorRole,
    RequestDomain,
    default_domain_for_role,
    is_request_domain_allowed_for_role,
    validate_actor_id,
    validate_class_id,
    validate_course_id,
)


class RequestContext(BaseModel):
    role: ActorRole
    actor_id: str
    course_id: str
    class_id: str
    domain: RequestDomain | None = None
    request_id: str
    idempotency_key: str | None = None


REVIEW_ROUTE_DOMAINS = {
    ActorRole.INSTRUCTOR: RequestDomain.ACADEMIC,
    ActorRole.OPERATOR: RequestDomain.OPERATIONS,
    ActorRole.VALIDATOR: RequestDomain.REVIEW,
    ActorRole.SYSTEM: RequestDomain.REVIEW,
}
REVIEW_MUTATION_ROLES = frozenset(
    {
        ActorRole.INSTRUCTOR,
        ActorRole.VALIDATOR,
        ActorRole.SYSTEM,
    }
)


def get_request_context(
    knowloop_role: str | None = Header(None, alias="X-Knowloop-Role"),
    knowloop_actor_id: str | None = Header(None, alias="X-Knowloop-Actor-Id"),
    knowloop_course_id: str | None = Header(None, alias="X-Knowloop-Course-Id"),
    knowloop_class_id: str | None = Header(None, alias="X-Knowloop-Class-Id"),
    knowloop_domain: str | None = Header(None, alias="X-Knowloop-Domain"),
    request_id: str | None = Header(None, alias="X-Request-Id"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> RequestContext:
    context = _build_request_context(
        knowloop_role=knowloop_role,
        knowloop_actor_id=knowloop_actor_id,
        knowloop_course_id=knowloop_course_id,
        knowloop_class_id=knowloop_class_id,
        knowloop_domain=knowloop_domain,
        request_id=request_id,
        idempotency_key=idempotency_key,
    )
    _assert_standard_domain_allowed(context)
    return context


def get_review_request_context(
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> RequestContext:
    expected_domain = REVIEW_ROUTE_DOMAINS.get(context.role)
    if expected_domain is None:
        raise ApiError(
            status_code=403,
            code="forbidden_scope",
            message="This role cannot access the review workflow.",
            request_id=context.request_id,
        )
    if context.domain is not expected_domain:
        raise ApiError(
            status_code=403,
            code="forbidden_scope",
            message=f"This role must use the {expected_domain.value} domain for review workflows.",
            request_id=context.request_id,
            details={
                "domain": context.domain.value if context.domain is not None else None,
                "role": context.role.value,
            },
        )
    return context


def get_mutating_review_request_context(
    context: Annotated[RequestContext, Depends(get_review_request_context)],
) -> RequestContext:
    if context.role not in REVIEW_MUTATION_ROLES:
        raise ApiError(
            status_code=403,
            code="forbidden_scope",
            message="This role cannot mutate review workflow candidates.",
            request_id=context.request_id,
            details={"role": context.role.value},
        )
    return require_idempotency_key(
        context,
        operation="review mutations",
    )


def require_idempotency_key(
    context: RequestContext,
    *,
    operation: str,
) -> RequestContext:
    if context.idempotency_key is None or not context.idempotency_key.strip():
        raise ApiError(
            status_code=422,
            code="validation_failed",
            message=f"Idempotency-Key is required for {operation}.",
            request_id=context.request_id,
        )
    return context


def _assert_standard_domain_allowed(context: RequestContext) -> None:
    if context.domain is None:
        return
    if not is_request_domain_allowed_for_role(context.role, context.domain):
        raise ApiError(
            status_code=422,
            code="validation_failed",
            message="This role cannot declare the requested X-Knowloop-Domain.",
            request_id=context.request_id,
            details={"domain": context.domain.value, "role": context.role.value},
        )


def _build_request_context(
    *,
    knowloop_role: str | None,
    knowloop_actor_id: str | None,
    knowloop_course_id: str | None,
    knowloop_class_id: str | None,
    knowloop_domain: str | None,
    request_id: str | None,
    idempotency_key: str | None,
) -> RequestContext:
    resolved_request_id = request_id or build_request_id()
    missing_headers = [
        header_name
        for header_name, value in (
            ("X-Knowloop-Role", knowloop_role),
            ("X-Knowloop-Actor-Id", knowloop_actor_id),
            ("X-Knowloop-Course-Id", knowloop_course_id),
            ("X-Knowloop-Class-Id", knowloop_class_id),
        )
        if value is None or not value.strip()
    ]
    if missing_headers:
        raise ApiError(
            status_code=422,
            code="missing_context",
            message="Missing required Knowloop request context headers.",
            request_id=resolved_request_id,
            details={"missing_headers": missing_headers},
        )

    try:
        role = ActorRole(knowloop_role)
    except ValueError as exc:
        raise ApiError(
            status_code=422,
            code="validation_failed",
            message="Unsupported X-Knowloop-Role value.",
            request_id=resolved_request_id,
            details={"role": knowloop_role},
        ) from exc

    domain = default_domain_for_role(role)
    if knowloop_domain is not None and knowloop_domain.strip():
        try:
            domain = RequestDomain(knowloop_domain)
        except ValueError as exc:
            raise ApiError(
                status_code=422,
                code="validation_failed",
                message="Unsupported X-Knowloop-Domain value.",
                request_id=resolved_request_id,
                details={"domain": knowloop_domain},
            ) from exc

    try:
        actor_id = validate_actor_id(knowloop_actor_id, actor_role=role)
        course_id = validate_course_id(knowloop_course_id)
        class_id = validate_class_id(knowloop_class_id)
    except ValueError as exc:
        field_name = str(exc).split(" ", maxsplit=1)[0]
        field_values = {
            "actor_id": knowloop_actor_id,
            "course_id": knowloop_course_id,
            "class_id": knowloop_class_id,
        }
        raise ApiError(
            status_code=422,
            code="validation_failed",
            message=str(exc),
            request_id=resolved_request_id,
            details={field_name: field_values.get(field_name)},
        ) from exc

    return RequestContext(
        role=role,
        actor_id=actor_id,
        course_id=course_id,
        class_id=class_id,
        domain=domain,
        request_id=resolved_request_id,
        idempotency_key=idempotency_key,
    )


def build_request_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"req-{timestamp}-{uuid4().hex[:8]}"
