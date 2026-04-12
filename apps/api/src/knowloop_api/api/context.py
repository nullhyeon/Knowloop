from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Header, Request
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
    domain_was_explicit: bool = False
    request_id: str
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class RouteDomainPolicy:
    allowed_domains: dict[ActorRole, RequestDomain]
    error_message: str
    domain_message: str
    forbidden_code: str = "forbidden_scope"
    forbidden_messages_by_role: dict[ActorRole, str] = field(default_factory=dict)
    forbidden_codes_by_role: dict[ActorRole, str] = field(default_factory=dict)


class RequestTracingContext(BaseModel):
    request_id: str
    client_request_id: str | None = None


REQUEST_TRACING_STATE_ATTR = "request_tracing_context"
REQUEST_ID_STATE_ATTR = "server_request_id"
CLIENT_REQUEST_ID_STATE_ATTR = "client_request_id"
CLIENT_REQUEST_ID_HEADER = "X-Request-Id"
CLIENT_REQUEST_ID_MAX_LENGTH = 128
CLIENT_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:/-]{1,128}$")
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
    }
)
INSTRUCTOR_INSIGHT_ROUTE_DOMAINS = {
    ActorRole.INSTRUCTOR: RequestDomain.ACADEMIC,
}
SESSION_SEARCH_ROUTE_DOMAINS = {
    ActorRole.STUDENT: RequestDomain.ACADEMIC,
    ActorRole.INSTRUCTOR: RequestDomain.ACADEMIC,
    ActorRole.OPERATOR: RequestDomain.OPERATIONS,
}
PUBLIC_QUERY_ROUTE_DOMAINS = {
    ActorRole.STUDENT: RequestDomain.ACADEMIC,
    ActorRole.INSTRUCTOR: RequestDomain.ACADEMIC,
    ActorRole.OPERATOR: RequestDomain.OPERATIONS,
    ActorRole.VALIDATOR: RequestDomain.REVIEW,
}
MAINTENANCE_REPORT_ROUTE_DOMAINS = {
    ActorRole.VALIDATOR: RequestDomain.REVIEW,
    ActorRole.SYSTEM: RequestDomain.REVIEW,
}
MAINTENANCE_STATUS_ROUTE_DOMAINS = {
    ActorRole.INSTRUCTOR: RequestDomain.ACADEMIC,
    ActorRole.VALIDATOR: RequestDomain.REVIEW,
    ActorRole.SYSTEM: RequestDomain.REVIEW,
}
ROUTE_DOMAIN_POLICIES = {
    "public_query": RouteDomainPolicy(
        allowed_domains=PUBLIC_QUERY_ROUTE_DOMAINS,
        error_message="This role cannot access the public query route.",
        domain_message="The public query route requires the expected domain for this role.",
        forbidden_messages_by_role={
            ActorRole.SYSTEM: "System role cannot use the public query route.",
        },
        forbidden_codes_by_role={
            ActorRole.SYSTEM: "forbidden_role",
        },
    ),
    "review": RouteDomainPolicy(
        allowed_domains=REVIEW_ROUTE_DOMAINS,
        error_message="This role cannot access the review workflow.",
        domain_message="This role must use the expected domain for review workflows.",
        forbidden_messages_by_role={
            ActorRole.STUDENT: "This role cannot access the review workflow.",
        },
        forbidden_codes_by_role={
            ActorRole.STUDENT: "forbidden_role",
        },
    ),
    "instructor_insight": RouteDomainPolicy(
        allowed_domains=INSTRUCTOR_INSIGHT_ROUTE_DOMAINS,
        error_message="This role cannot access instructor insight workflows.",
        domain_message="Instructor insight workflows require the expected domain for this role.",
    ),
    "session_search": RouteDomainPolicy(
        allowed_domains=SESSION_SEARCH_ROUTE_DOMAINS,
        error_message="This role cannot access the session search routes.",
        domain_message="Session search routes require the expected domain for this role.",
    ),
    "maintenance_report": RouteDomainPolicy(
        allowed_domains=MAINTENANCE_REPORT_ROUTE_DOMAINS,
        error_message="This role cannot run maintenance reports.",
        domain_message="Maintenance report runs require the expected domain for this role.",
    ),
    "maintenance_status": RouteDomainPolicy(
        allowed_domains=MAINTENANCE_STATUS_ROUTE_DOMAINS,
        error_message="This role cannot view maintenance status.",
        domain_message="Maintenance status requires the expected domain for this role.",
    ),
}


def get_request_context(
    request: Request,
    knowloop_role: str | None = Header(None, alias="X-Knowloop-Role"),
    knowloop_actor_id: str | None = Header(None, alias="X-Knowloop-Actor-Id"),
    knowloop_course_id: str | None = Header(None, alias="X-Knowloop-Course-Id"),
    knowloop_class_id: str | None = Header(None, alias="X-Knowloop-Class-Id"),
    knowloop_domain: str | None = Header(None, alias="X-Knowloop-Domain"),
    client_request_id: str | None = Header(None, alias="X-Request-Id"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> RequestContext:
    del client_request_id
    ensure_request_tracing_context(request, extract_client_request_id(request))
    context = _build_request_context(
        knowloop_role=knowloop_role,
        knowloop_actor_id=knowloop_actor_id,
        knowloop_course_id=knowloop_course_id,
        knowloop_class_id=knowloop_class_id,
        knowloop_domain=knowloop_domain,
        resolved_request_id=get_server_request_id(request),
        idempotency_key=idempotency_key,
        preserve_omitted_domain=False,
    )
    _assert_standard_domain_allowed(context)
    return context


def get_public_query_request_context(
    request: Request,
    knowloop_role: str | None = Header(None, alias="X-Knowloop-Role"),
    knowloop_actor_id: str | None = Header(None, alias="X-Knowloop-Actor-Id"),
    knowloop_course_id: str | None = Header(None, alias="X-Knowloop-Course-Id"),
    knowloop_class_id: str | None = Header(None, alias="X-Knowloop-Class-Id"),
    knowloop_domain: str | None = Header(None, alias="X-Knowloop-Domain"),
    client_request_id: str | None = Header(None, alias="X-Request-Id"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> RequestContext:
    del client_request_id
    ensure_request_tracing_context(request, extract_client_request_id(request))
    context = _build_request_context(
        knowloop_role=knowloop_role,
        knowloop_actor_id=knowloop_actor_id,
        knowloop_course_id=knowloop_course_id,
        knowloop_class_id=knowloop_class_id,
        knowloop_domain=knowloop_domain,
        resolved_request_id=get_server_request_id(request),
        idempotency_key=idempotency_key,
        preserve_omitted_domain=True,
    )
    _assert_standard_domain_allowed(context)
    if not context.domain_was_explicit:
        expected_domain = ROUTE_DOMAIN_POLICIES["public_query"].allowed_domains.get(context.role)
        if expected_domain is not None:
            context = context.model_copy(
                update={"domain": expected_domain, "domain_was_explicit": False}
            )
    return _require_route_domain(context, policy=ROUTE_DOMAIN_POLICIES["public_query"])


def get_review_request_context(
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> RequestContext:
    if (
        context.role is ActorRole.SYSTEM
        and context.domain is None
        and not context.domain_was_explicit
    ):
        raise ApiError(
            status_code=422,
            code="validation_failed",
            message="System review requests must declare X-Knowloop-Domain: review.",
            request_id=context.request_id,
            details={"role": context.role.value, "expected_domain": RequestDomain.REVIEW.value},
        )
    return _require_route_domain(context, policy=ROUTE_DOMAIN_POLICIES["review"])


def get_mutating_review_request_context(
    context: Annotated[RequestContext, Depends(get_review_request_context)],
) -> RequestContext:
    if context.role not in REVIEW_MUTATION_ROLES:
        raise ApiError(
            status_code=403,
            code="forbidden_role",
            message="This role cannot mutate review workflow candidates.",
            request_id=context.request_id,
            details={"role": context.role.value},
        )
    return require_idempotency_key(
        context,
        operation="review mutations",
    )


def get_instructor_insight_request_context(
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> RequestContext:
    return _require_route_domain(context, policy=ROUTE_DOMAIN_POLICIES["instructor_insight"])


def get_session_search_request_context(
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> RequestContext:
    return _require_route_domain(context, policy=ROUTE_DOMAIN_POLICIES["session_search"])


def get_maintenance_report_request_context(
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> RequestContext:
    return _require_route_domain(context, policy=ROUTE_DOMAIN_POLICIES["maintenance_report"])


def get_maintenance_status_request_context(
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> RequestContext:
    return _require_route_domain(context, policy=ROUTE_DOMAIN_POLICIES["maintenance_status"])


def _require_route_domain(
    context: RequestContext,
    *,
    policy: RouteDomainPolicy,
) -> RequestContext:
    expected_domain = policy.allowed_domains.get(context.role)
    if expected_domain is None:
        raise ApiError(
            status_code=403,
            code=policy.forbidden_codes_by_role.get(context.role, policy.forbidden_code),
            message=policy.forbidden_messages_by_role.get(context.role, policy.error_message),
            request_id=context.request_id,
        )
    if context.domain is not expected_domain:
        raise ApiError(
            status_code=403,
            code="forbidden_scope",
            message=policy.domain_message,
            request_id=context.request_id,
            details={
                "domain": context.domain.value if context.domain is not None else None,
                "role": context.role.value,
                "expected_domain": expected_domain.value,
            },
        )
    return context


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


def get_server_request_id(request: Request) -> str:
    tracing = getattr(request.state, REQUEST_TRACING_STATE_ATTR, None)
    if isinstance(tracing, RequestTracingContext):
        return tracing.request_id
    return ensure_request_tracing_context(request).request_id


def ensure_request_tracing_context(
    request: Request,
    client_request_id: str | None = None,
) -> RequestTracingContext:
    tracing = getattr(request.state, REQUEST_TRACING_STATE_ATTR, None)
    if isinstance(tracing, RequestTracingContext):
        if tracing.client_request_id is None and client_request_id is not None:
            tracing = tracing.model_copy(
                update={"client_request_id": normalize_client_request_id(client_request_id)}
            )
            attach_request_tracing_context(request, tracing)
        return tracing

    tracing = build_request_tracing_context(client_request_id)
    attach_request_tracing_context(request, tracing)
    return tracing


def extract_client_request_id(request: Request) -> str | None:
    raw_values = request.headers.getlist(CLIENT_REQUEST_ID_HEADER)
    if len(raw_values) != 1:
        return None

    raw_value = raw_values[0]
    if "," in raw_value:
        return None
    if raw_value != raw_value.strip():
        return None

    return normalize_client_request_id(raw_value)


def build_request_tracing_context(client_request_id: str | None) -> RequestTracingContext:
    return RequestTracingContext(
        request_id=build_request_id(),
        client_request_id=normalize_client_request_id(client_request_id),
    )


def attach_request_tracing_context(
    request: Request,
    tracing: RequestTracingContext,
) -> None:
    setattr(request.state, REQUEST_TRACING_STATE_ATTR, tracing)
    setattr(request.state, REQUEST_ID_STATE_ATTR, tracing.request_id)
    set_client_request_id(request, tracing.client_request_id)


def get_request_tracing_context(request: Request) -> RequestTracingContext:
    return ensure_request_tracing_context(request)


def get_client_request_id(request: Request) -> str | None:
    tracing = getattr(request.state, REQUEST_TRACING_STATE_ATTR, None)
    if isinstance(tracing, RequestTracingContext):
        return normalize_client_request_id(tracing.client_request_id)
    return normalize_client_request_id(
        getattr(request.state, CLIENT_REQUEST_ID_STATE_ATTR, None),
    )


def set_client_request_id(request: Request, request_id: str | None) -> None:
    normalized = normalize_client_request_id(request_id)
    tracing = getattr(request.state, REQUEST_TRACING_STATE_ATTR, None)
    if isinstance(tracing, RequestTracingContext):
        setattr(
            request.state,
            REQUEST_TRACING_STATE_ATTR,
            tracing.model_copy(update={"client_request_id": normalized}),
        )
    if normalized is None:
        if hasattr(request.state, CLIENT_REQUEST_ID_STATE_ATTR):
            delattr(request.state, CLIENT_REQUEST_ID_STATE_ATTR)
        return
    setattr(request.state, CLIENT_REQUEST_ID_STATE_ATTR, normalized)


def normalize_client_request_id(request_id: str | None) -> str | None:
    if not isinstance(request_id, str):
        return None
    if not request_id:
        return None
    if len(request_id) > CLIENT_REQUEST_ID_MAX_LENGTH:
        return None
    if CLIENT_REQUEST_ID_PATTERN.fullmatch(request_id) is None:
        return None
    return request_id


def _build_request_context(
    *,
    knowloop_role: str | None,
    knowloop_actor_id: str | None,
    knowloop_course_id: str | None,
    knowloop_class_id: str | None,
    knowloop_domain: str | None,
    resolved_request_id: str,
    idempotency_key: str | None,
    preserve_omitted_domain: bool,
) -> RequestContext:
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

    domain = None if preserve_omitted_domain else default_domain_for_role(role)
    domain_was_explicit = False
    if knowloop_domain is not None and knowloop_domain.strip():
        domain_was_explicit = True
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
        domain_was_explicit=domain_was_explicit,
        request_id=resolved_request_id,
        idempotency_key=idempotency_key,
    )


def build_request_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"req-{timestamp}-{uuid4().hex[:8]}"
