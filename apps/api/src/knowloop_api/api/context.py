from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Header
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


def get_request_context(
    knowloop_role: str | None = Header(None, alias="X-Knowloop-Role"),
    knowloop_actor_id: str | None = Header(None, alias="X-Knowloop-Actor-Id"),
    knowloop_course_id: str | None = Header(None, alias="X-Knowloop-Course-Id"),
    knowloop_class_id: str | None = Header(None, alias="X-Knowloop-Class-Id"),
    knowloop_domain: str | None = Header(None, alias="X-Knowloop-Domain"),
    request_id: str | None = Header(None, alias="X-Request-Id"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
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
        if not is_request_domain_allowed_for_role(role, domain):
            raise ApiError(
                status_code=422,
                code="validation_failed",
                message="This role cannot declare the requested X-Knowloop-Domain.",
                request_id=resolved_request_id,
                details={"domain": domain.value, "role": role.value},
            )

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
