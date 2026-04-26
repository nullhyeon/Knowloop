from __future__ import annotations

import hmac
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Header, Request
from pydantic import BaseModel

from knowloop_api.api.errors import ApiError
from knowloop_api.core.config import Settings, get_settings
from knowloop_api.core.contracts import (
    ActorRole,
    RequestDomain,
    default_domain_for_role,
    is_request_domain_allowed_for_role,
    validate_actor_id,
    validate_class_id,
    validate_course_id,
)
from knowloop_api.core.input_limits import MAX_IDEMPOTENCY_KEY_LENGTH
from knowloop_api.services.context_profiles import (
    ContextProfile,
    ContextProfileNotFoundError,
    get_context_profile,
)


class RequestContext(BaseModel):
    profile_id: str | None = None
    profile_label: str | None = None
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
IDEMPOTENCY_KEY_PATTERN = re.compile(
    rf"^[A-Za-z0-9._:/-]{{1,{MAX_IDEMPOTENCY_KEY_LENGTH}}}$"
)
CONTEXT_TIMESTAMP_HEADER = "X-Knowloop-Context-Timestamp"
CONTEXT_SIGNATURE_HEADER = "X-Knowloop-Context-Signature"
CONTEXT_SIGNATURE_PREFIX = "v1="
CONTEXT_SIGNATURE_PAYLOAD_VERSION = "knowloop-context-v1"
CONTEXT_SIGNATURE_MAX_FUTURE_SKEW_SECONDS = 30
CONTEXT_SIGNATURE_HEADERS = (
    "X-Knowloop-Profile-Id",
    "X-Knowloop-Role",
    "X-Knowloop-Actor-Id",
    "X-Knowloop-Course-Id",
    "X-Knowloop-Class-Id",
    "X-Knowloop-Domain",
)
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
LEARNING_SELF_ROUTE_DOMAINS = {
    ActorRole.STUDENT: RequestDomain.ACADEMIC,
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
    "learning_self": RouteDomainPolicy(
        allowed_domains=LEARNING_SELF_ROUTE_DOMAINS,
        error_message="This role cannot view the personal learning console.",
        domain_message="The personal learning console requires the expected domain for this role.",
    ),
}


def get_request_context(
    request: Request,
    knowloop_profile_id: str | None = Header(None, alias="X-Knowloop-Profile-Id"),
    knowloop_role: str | None = Header(None, alias="X-Knowloop-Role"),
    knowloop_actor_id: str | None = Header(None, alias="X-Knowloop-Actor-Id"),
    knowloop_course_id: str | None = Header(None, alias="X-Knowloop-Course-Id"),
    knowloop_class_id: str | None = Header(None, alias="X-Knowloop-Class-Id"),
    knowloop_domain: str | None = Header(None, alias="X-Knowloop-Domain"),
    client_request_id: str | None = Header(None, alias="X-Request-Id"),
) -> RequestContext:
    del client_request_id
    ensure_request_tracing_context(request, extract_client_request_id(request))
    _assert_request_context_trusted(request, get_server_request_id(request))
    context = _build_request_context(
        request=request,
        knowloop_profile_id=knowloop_profile_id,
        knowloop_role=knowloop_role,
        knowloop_actor_id=knowloop_actor_id,
        knowloop_course_id=knowloop_course_id,
        knowloop_class_id=knowloop_class_id,
        knowloop_domain=knowloop_domain,
        resolved_request_id=get_server_request_id(request),
        idempotency_key=extract_idempotency_key(request, get_server_request_id(request)),
        preserve_omitted_domain=False,
    )
    _assert_standard_domain_allowed(context)
    return context


def get_public_query_request_context(
    request: Request,
    knowloop_profile_id: str | None = Header(None, alias="X-Knowloop-Profile-Id"),
    knowloop_role: str | None = Header(None, alias="X-Knowloop-Role"),
    knowloop_actor_id: str | None = Header(None, alias="X-Knowloop-Actor-Id"),
    knowloop_course_id: str | None = Header(None, alias="X-Knowloop-Course-Id"),
    knowloop_class_id: str | None = Header(None, alias="X-Knowloop-Class-Id"),
    knowloop_domain: str | None = Header(None, alias="X-Knowloop-Domain"),
    client_request_id: str | None = Header(None, alias="X-Request-Id"),
) -> RequestContext:
    del client_request_id
    ensure_request_tracing_context(request, extract_client_request_id(request))
    _assert_request_context_trusted(request, get_server_request_id(request))
    context = _build_request_context(
        request=request,
        knowloop_profile_id=knowloop_profile_id,
        knowloop_role=knowloop_role,
        knowloop_actor_id=knowloop_actor_id,
        knowloop_course_id=knowloop_course_id,
        knowloop_class_id=knowloop_class_id,
        knowloop_domain=knowloop_domain,
        resolved_request_id=get_server_request_id(request),
        idempotency_key=extract_idempotency_key(request, get_server_request_id(request)),
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


def get_learning_self_request_context(
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> RequestContext:
    return _require_route_domain(context, policy=ROUTE_DOMAIN_POLICIES["learning_self"])


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


def extract_idempotency_key(request: Request, request_id: str) -> str | None:
    raw_values = request.headers.getlist("Idempotency-Key")
    if not raw_values:
        return None
    if len(raw_values) != 1:
        raise ApiError(
            status_code=422,
            code="validation_failed",
            message="Idempotency-Key must be sent as a single canonical header.",
            request_id=request_id,
            details={"header": "Idempotency-Key"},
        )
    raw_value = raw_values[0]
    if "," in raw_value:
        raise ApiError(
            status_code=422,
            code="validation_failed",
            message="Idempotency-Key must be sent as a single canonical header.",
            request_id=request_id,
            details={"header": "Idempotency-Key"},
        )
    return normalize_idempotency_key(raw_value, request_id)


def normalize_idempotency_key(idempotency_key: str | None, request_id: str) -> str | None:
    if not isinstance(idempotency_key, str):
        return None
    normalized = idempotency_key.strip()
    if not normalized:
        return None
    if len(normalized) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise ApiError(
            status_code=422,
            code="validation_failed",
            message="Idempotency-Key exceeds the supported length.",
            request_id=request_id,
            details={
                "header": "Idempotency-Key",
                "max_length": MAX_IDEMPOTENCY_KEY_LENGTH,
            },
        )
    if IDEMPOTENCY_KEY_PATTERN.fullmatch(normalized) is None:
        raise ApiError(
            status_code=422,
            code="validation_failed",
            message="Idempotency-Key contains unsupported characters.",
            request_id=request_id,
            details={
                "header": "Idempotency-Key",
                "allowed_characters": "letters, digits, '.', '_', ':', '/', '-'",
            },
        )
    return normalized


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


def _get_request_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, Settings):
        return settings
    return get_settings()


def _assert_request_context_trusted(request: Request, request_id: str) -> None:
    settings = _get_request_settings(request)
    profile_id = _read_optional_single_header(request, "X-Knowloop-Profile-Id", request_id)
    if profile_id and not settings.demo_context_profiles_enabled:
        raise ApiError(
            status_code=403,
            code="demo_profiles_disabled",
            message="Context profiles are disabled outside explicit demo mode.",
            request_id=request_id,
        )
    if settings.context_trust_mode != "signed":
        return
    _assert_signed_context_headers(request, settings, request_id)


def _assert_signed_context_headers(
    request: Request,
    settings: Settings,
    request_id: str,
) -> None:
    missing_headers = [
        header_name
        for header_name in (CONTEXT_TIMESTAMP_HEADER, CONTEXT_SIGNATURE_HEADER)
        if not request.headers.getlist(header_name)
    ]
    if missing_headers:
        raise ApiError(
            status_code=403,
            code="untrusted_context",
            message="Knowloop request context is missing a trusted signature.",
            request_id=request_id,
            details={"missing_headers": missing_headers},
        )

    timestamp = _read_required_single_header(request, CONTEXT_TIMESTAMP_HEADER, request_id)
    signature = _read_required_single_header(request, CONTEXT_SIGNATURE_HEADER, request_id)
    try:
        timestamp_seconds = int(timestamp)
    except ValueError as exc:
        raise _invalid_context_signature_error(
            request_id,
            details={"header": CONTEXT_TIMESTAMP_HEADER},
        ) from exc

    now_seconds = int(time.time())
    if timestamp_seconds - now_seconds > CONTEXT_SIGNATURE_MAX_FUTURE_SKEW_SECONDS:
        raise _invalid_context_signature_error(
            request_id,
            details={"max_future_skew_seconds": CONTEXT_SIGNATURE_MAX_FUTURE_SKEW_SECONDS},
        )
    if now_seconds - timestamp_seconds > settings.trusted_context_max_age_seconds:
        raise _invalid_context_signature_error(
            request_id,
            details={"max_age_seconds": settings.trusted_context_max_age_seconds},
        )

    if not signature.startswith(CONTEXT_SIGNATURE_PREFIX):
        raise _invalid_context_signature_error(
            request_id,
            details={"header": CONTEXT_SIGNATURE_HEADER},
        )

    secret = settings.trusted_context_secret
    if secret is None:
        raise _invalid_context_signature_error(request_id, details={"adapter": "signed_headers"})
    expected_signature = _build_context_signature(
        secret=secret.get_secret_value(),
        payload=_build_context_signature_payload(request, timestamp),
    )
    if not hmac.compare_digest(signature, f"{CONTEXT_SIGNATURE_PREFIX}{expected_signature}"):
        raise _invalid_context_signature_error(request_id, details={"adapter": "signed_headers"})


def _read_optional_single_header(
    request: Request,
    header_name: str,
    request_id: str,
) -> str | None:
    raw_values = request.headers.getlist(header_name)
    if not raw_values:
        return None
    return _normalize_trusted_context_header_value(
        header_name=header_name,
        raw_values=raw_values,
        request_id=request_id,
        allow_empty=True,
    )


def _read_required_single_header(request: Request, header_name: str, request_id: str) -> str:
    return _normalize_trusted_context_header_value(
        header_name=header_name,
        raw_values=request.headers.getlist(header_name),
        request_id=request_id,
        allow_empty=False,
    )


def _normalize_trusted_context_header_value(
    *,
    header_name: str,
    raw_values: list[str],
    request_id: str,
    allow_empty: bool,
) -> str:
    if len(raw_values) != 1:
        raise _invalid_context_signature_error(request_id, details={"header": header_name})
    value = raw_values[0]
    if "," in value or value != value.strip():
        raise _invalid_context_signature_error(request_id, details={"header": header_name})
    if not allow_empty and not value:
        raise _invalid_context_signature_error(request_id, details={"header": header_name})
    return value


def _build_context_signature_payload(request: Request, timestamp: str) -> str:
    lines = [
        CONTEXT_SIGNATURE_PAYLOAD_VERSION,
        request.method.upper(),
        request.url.path,
        timestamp,
    ]
    for header_name in CONTEXT_SIGNATURE_HEADERS:
        raw_values = request.headers.getlist(header_name)
        header_value = ""
        if raw_values:
            header_value = _normalize_trusted_context_header_value(
                header_name=header_name,
                raw_values=raw_values,
                request_id=get_server_request_id(request),
                allow_empty=True,
            )
        lines.append(f"{header_name.lower()}:{header_value}")
    return "\n".join(lines)


def _build_context_signature(*, secret: str, payload: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        "sha256",
    ).hexdigest()


def _invalid_context_signature_error(
    request_id: str,
    *,
    details: dict[str, object],
) -> ApiError:
    return ApiError(
        status_code=403,
        code="untrusted_context",
        message="Knowloop request context is missing, expired, or invalid.",
        request_id=request_id,
        details=details,
    )


def _resolve_context_profile(
    *,
    request: Request,
    profile_id: str | None,
    request_id: str,
) -> ContextProfile | None:
    normalized_profile_id = profile_id.strip() if isinstance(profile_id, str) else None
    if not normalized_profile_id:
        return None

    try:
        return get_context_profile(_get_request_settings(request), normalized_profile_id)
    except ContextProfileNotFoundError as exc:
        raise ApiError(
            status_code=422,
            code="validation_failed",
            message="Unknown X-Knowloop-Profile-Id value.",
            request_id=request_id,
            details={"profile_id": normalized_profile_id},
        ) from exc


def _resolve_context_fields_from_headers_or_profile(
    *,
    profile: ContextProfile | None,
    knowloop_role: str | None,
    knowloop_actor_id: str | None,
    knowloop_course_id: str | None,
    knowloop_class_id: str | None,
    knowloop_domain: str | None,
    request_id: str,
) -> dict[str, str | None]:
    if profile is None:
        return {
            "role": knowloop_role,
            "actor_id": knowloop_actor_id,
            "course_id": knowloop_course_id,
            "class_id": knowloop_class_id,
            "domain": knowloop_domain,
        }

    profile_values = {
        "role": profile.role.value,
        "actor_id": profile.actor_id,
        "course_id": profile.course_id,
        "class_id": profile.class_id,
        "domain": profile.domain.value,
    }
    provided_values = {
        "role": knowloop_role,
        "actor_id": knowloop_actor_id,
        "course_id": knowloop_course_id,
        "class_id": knowloop_class_id,
        "domain": knowloop_domain,
    }

    conflicts = [
        key
        for key, value in provided_values.items()
        if value is not None and value.strip() and value.strip() != profile_values[key]
    ]
    if conflicts:
        raise ApiError(
            status_code=422,
            code="validation_failed",
            message="X-Knowloop-Profile-Id conflicts with explicit Knowloop context headers.",
            request_id=request_id,
            details={
                "profile_id": profile.profile_id,
                "conflicting_fields": conflicts,
            },
        )

    return profile_values


def _build_request_context(
    *,
    request: Request,
    knowloop_profile_id: str | None,
    knowloop_role: str | None,
    knowloop_actor_id: str | None,
    knowloop_course_id: str | None,
    knowloop_class_id: str | None,
    knowloop_domain: str | None,
    resolved_request_id: str,
    idempotency_key: str | None,
    preserve_omitted_domain: bool,
) -> RequestContext:
    profile = _resolve_context_profile(
        request=request,
        profile_id=knowloop_profile_id,
        request_id=resolved_request_id,
    )
    resolved_fields = _resolve_context_fields_from_headers_or_profile(
        profile=profile,
        knowloop_role=knowloop_role,
        knowloop_actor_id=knowloop_actor_id,
        knowloop_course_id=knowloop_course_id,
        knowloop_class_id=knowloop_class_id,
        knowloop_domain=knowloop_domain,
        request_id=resolved_request_id,
    )
    missing_headers = [
        header_name
        for header_name, value in (
            ("X-Knowloop-Role", resolved_fields["role"]),
            ("X-Knowloop-Actor-Id", resolved_fields["actor_id"]),
            ("X-Knowloop-Course-Id", resolved_fields["course_id"]),
            ("X-Knowloop-Class-Id", resolved_fields["class_id"]),
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
        role = ActorRole(resolved_fields["role"])
    except ValueError as exc:
        raise ApiError(
            status_code=422,
            code="validation_failed",
            message="Unsupported X-Knowloop-Role value.",
            request_id=resolved_request_id,
            details={"role": resolved_fields["role"]},
        ) from exc

    domain = None if preserve_omitted_domain else default_domain_for_role(role)
    domain_was_explicit = False
    resolved_domain_value = resolved_fields["domain"]
    if resolved_domain_value is not None and resolved_domain_value.strip():
        domain_was_explicit = True
        try:
            domain = RequestDomain(resolved_domain_value)
        except ValueError as exc:
            raise ApiError(
                status_code=422,
                code="validation_failed",
                message="Unsupported X-Knowloop-Domain value.",
                request_id=resolved_request_id,
                details={"domain": resolved_domain_value},
            ) from exc
        if profile is not None:
            domain_was_explicit = False

    try:
        actor_id = validate_actor_id(resolved_fields["actor_id"], actor_role=role)
        course_id = validate_course_id(resolved_fields["course_id"])
        class_id = validate_class_id(resolved_fields["class_id"])
    except ValueError as exc:
        field_name = str(exc).split(" ", maxsplit=1)[0]
        field_values = {
            "actor_id": resolved_fields["actor_id"],
            "course_id": resolved_fields["course_id"],
            "class_id": resolved_fields["class_id"],
        }
        raise ApiError(
            status_code=422,
            code="validation_failed",
            message=str(exc),
            request_id=resolved_request_id,
            details={field_name: field_values.get(field_name)},
        ) from exc

    return RequestContext(
        profile_id=profile.profile_id if profile is not None else None,
        profile_label=profile.label if profile is not None else None,
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
