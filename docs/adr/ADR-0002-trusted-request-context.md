# ADR-0002: Trusted Request Context Adapter

## Status

Accepted

## Date

2026-04-26

## Context

Knowloop routes make authorization decisions from request context: role, actor, course,
class, and domain. The MVP originally accepted those fields directly from
`X-Knowloop-*` headers so fixture-driven backend and frontend work could move quickly.

That header contract is useful for local demos, but it is not a production security
boundary. A caller that can set those headers can forge instructor, validator, or system
scope.

## Decision

Keep the internal `RequestContext` shape and route-level role/domain policies, but make
the request-context boundary configurable:

- `context_trust_mode=legacy_headers` remains the development and local demo mode.
- `context_trust_mode=signed` requires `X-Knowloop-Context-Timestamp` and
  `X-Knowloop-Context-Signature`.
- Production settings must use signed mode and must provide `trusted_context_secret`.
- Signed mode requires `trusted_context_secret` to be at least 32 bytes.
- The signed payload covers method, API path, timestamp, and canonical context header
  values.
- Old timestamps are bounded by `trusted_context_max_age_seconds`; future timestamps are
  accepted only within a fixed 30-second skew window.
- `X-Request-Id` and `Idempotency-Key` stay outside the signature because they are
  tracing and replay controls, not authorization inputs.
- Demo profile lookup and `GET /api/v1/context/profiles` are available only when
  `demo_context_profiles_enabled=true`.

## Consequences

### Positive

- production deployments no longer accept forgeable role and scope headers by default
- existing route, service, and storage code can continue using `RequestContext`
- local fixture and demo workflows remain available in explicit demo/development mode
- a future full authentication layer can replace the signed adapter without changing
  downstream domain policies

### Negative

- clients in signed mode need a trusted upstream signer or test helper
- invalid context now fails before route-specific authorization checks
- demo profile behavior is no longer a public unauthenticated contract outside demo mode

## Follow-Up

- replace the signed adapter with a real user-auth/session adapter when an identity
  provider is selected
- add request size and field bounds across query, source, and review payloads
