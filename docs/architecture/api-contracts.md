# Knowloop API Contracts

## 1. Purpose

This document defines the HTTP contract for the current Knowloop MVP backend.
It focuses on the routes that already exist or are locked for the immediate backend slices.

## 2. Design Rules

1. API boundaries must reflect role boundaries.
2. Formal wiki is never edited directly through the public query route.
3. Mutating routes should be replay-safe when an `Idempotency-Key` is supplied.
4. Success and error envelopes stay consistent across endpoints.
5. Query routes return both the answer and the write-back plan because Knowloop is a memory workflow, not a plain chat completion API.

## 3. Base URL and Formats

Base path:

```text
/api/v1
```

Two health route families are implemented:

- `GET /healthz`
- `GET /readyz`
- `GET /api/v1/system/health`
- `GET /api/v1/system/ready`

Intent:

- top-level routes are the canonical probe paths for runtime liveness and readiness
- versioned system routes expose the same health information inside the normal API surface

Content type:

- request: `application/json`
- response: `application/json`

Timestamps use UTC ISO 8601 strings.

Request bounds:

- every body-consuming `/api/v1/*` `POST`, `PUT`, and `PATCH` route is subject to a deployment cap from `max_api_request_body_bytes`, default `1048576`
- route-level caps are lower where the workflow should stay compact:
  - `POST /api/v1/query/respond`: `16384` bytes
  - `POST /api/v1/sources/register`: `262144` bytes
  - `POST /api/v1/review/candidates/*`: `8192` bytes
- the effective body limit is the lower of the route cap and `max_api_request_body_bytes`
- body-size enforcement happens before route parsing when `Content-Length` exceeds the effective limit, and while the route consumes the request body for clients that stream without a truthful `Content-Length`
- body-size failures return `413 body_too_large` with `details.route` and `details.limit_bytes`
- field, list, path, query, and header bounds return `422 validation_failed` through the standard validation envelope unless a route documents a narrower business error

## 4. Request Context Boundary

Protected non-system routes use request context fields. The fields may arrive through a
trusted signed-header adapter or through the legacy development/demo header adapter.
`GET /api/v1/context/profiles` is the one bootstrap exception: it does not resolve a
request context and is guarded only by `demo_context_profiles_enabled`.

Runtime modes:

- `context_trust_mode=legacy_headers`
  - development and local demo compatibility mode
  - accepts bare `X-Knowloop-*` context headers
  - must not be used for production
- `context_trust_mode=signed`
  - production-safe adapter for deployments that do not yet have full user authentication
  - accepts the same logical context headers only when the request also carries a valid trusted context signature
  - `app_env=production` refuses to start unless this mode is enabled
  - `app_env=production` also refuses to start when demo context profiles are enabled

The signed-header adapter requires:

- `X-Knowloop-Context-Timestamp`
- `X-Knowloop-Context-Signature`

Signature rules:

- signature format is `v1=<hex-hmac-sha256>`
- the HMAC secret comes from `trusted_context_secret`
- `trusted_context_secret` must be at least 32 bytes in signed mode
- `X-Knowloop-Context-Timestamp` is a Unix epoch timestamp in whole seconds, not an ISO timestamp
- the signature covers method, API path, timestamp, and the canonical `X-Knowloop-*` context header values
- omitted optional context headers are signed as empty values
- `X-Request-Id` and `Idempotency-Key` are not signed because they remain transport tracing and replay controls, not authorization inputs
- expired, malformed, duplicate, comma-joined, or mismatched signed-context inputs fail with `403 untrusted_context`

Canonical signed payload:

```text
knowloop-context-v1
<UPPERCASE_HTTP_METHOD>
<API_PATH_ONLY>
<UNIX_EPOCH_SECONDS>
x-knowloop-profile-id:<value-or-empty>
x-knowloop-role:<value-or-empty>
x-knowloop-actor-id:<value-or-empty>
x-knowloop-course-id:<value-or-empty>
x-knowloop-class-id:<value-or-empty>
x-knowloop-domain:<value-or-empty>
```

Payload notes:

- lines are joined with `\n`
- header names are lower-case and appear in the exact order above
- the path is `request.url.path` only; query strings are not included
- duplicate header values, comma-joined values, and leading/trailing whitespace are rejected before signature comparison
- old timestamps are accepted only within `trusted_context_max_age_seconds`
- future timestamps are accepted only within the fixed clock-skew window of 30 seconds

Required headers:

- `X-Knowloop-Role`
- `X-Knowloop-Actor-Id`
- `X-Knowloop-Course-Id`
- `X-Knowloop-Class-Id`

Optional headers:

- `X-Knowloop-Profile-Id`
- `X-Knowloop-Domain`
- `X-Request-Id`
- `Idempotency-Key`

Header notes:

- `Request Context Default Domains v1`:
  - `student` -> `academic`
  - `instructor` -> `academic`
  - `operator` -> `operations`
  - `validator` -> `review`
- `X-Request-Id` in the response is the authoritative application-owned tracing ID for that HTTP attempt; the Knowloop API application generates it and upstream layers must preserve it rather than replace it.
- if a client sends `X-Request-Id`, the server replaces it with a fresh server-owned attempt-local tracing ID; replay semantics and recovery ownership never depend on a client-supplied tracing header.
- when a client supplied `X-Request-Id` is present, the API must echo it back in `X-Client-Request-Id` for cross-service correlation on both success and error responses while keeping `X-Request-Id` server-owned.
- `X-Client-Request-Id` reflection is best-effort and validation-gated:
  - accepted characters: letters, digits, `.`, `_`, `:`, `/`, `-`
  - maximum length: `128`
  - invalid or oversized values are dropped instead of being reflected
  - duplicate, comma-joined, or otherwise multi-value inputs are treated as non-canonical and dropped instead of being reflected
  - reflected values are transport-only metadata and must not be persisted into session, candidate, wiki, learning, audit, or mutation artifacts
- `Idempotency-Key` is the replay-safe mutation key for routes that support retry semantics.
- `Idempotency-Key` is trimmed before replay ownership is evaluated; accepted characters are letters, digits, `.`, `_`, `:`, `/`, and `-`, and the maximum length is `128`.
- duplicate or comma-joined `Idempotency-Key` values fail with `422 validation_failed` because replay ownership requires one canonical key per HTTP attempt.
- `X-Knowloop-Profile-Id` is a frontend/bootstrap adapter for demo and local UI flows:
  - it is accepted only when `demo_context_profiles_enabled=true`
  - when present, the API resolves the role, actor, course, class, and default domain from the checked-in context profile registry
  - when omitted, the route still uses the explicit `X-Knowloop-*` header contract
  - if `X-Knowloop-Profile-Id` is sent together with explicit `X-Knowloop-*` values, every provided explicit field must match the profile exactly or the request fails with `422 validation_failed`
  - `X-Knowloop-Profile-Id` does not replace `Idempotency-Key` or the tracing headers; it only resolves the scoped actor context
  - when demo profiles are disabled, any use of `X-Knowloop-Profile-Id` fails with `403 demo_profiles_disabled`
- role and domain combinations must satisfy the role-permission contract.
- when `X-Knowloop-Domain` is omitted, the shared request-context dependency first resolves the role's default domain using `Request Context Default Domains v1` only for roles listed in that table
- `system` has no shared request-context default domain; omitted-domain behavior for `system` must be declared per route family
- `Request Context Default Domains v1` is the shared permission-default table for route families that do not define their own replay normalization; route-local replay contracts may intentionally restate the same mapping to freeze behavior at that boundary
- replay/idempotency normalization is route-specific and is locked at each mutating endpoint instead of being implied by the shared header contract
- routes that allow `system` must document whether omitted `X-Knowloop-Domain` is accepted or whether an explicit domain is required for that route family
- dedicated review endpoints still use role-specific domain ownership:
  - `instructor` review requests use `academic`
  - `operator` review requests use `operations`
  - `validator` and `system` review requests use `review`
- `/api/v1/review/*` is the workflow boundary for candidate promotion actions; `X-Knowloop-Domain` alone does not grant review authority.
- every `/api/v1/*` response must emit `X-Request-Id`; probe routes such as `/`, `/healthz`, and `/readyz` stay outside the API envelope contract

Context bootstrap routes:

- `GET /api/v1/context/profiles`
  - returns the demo/frontend profile registry that can be used to seed UI role switching without handcrafting verbose request headers
  - available only when `demo_context_profiles_enabled=true`
  - otherwise fails with `403 demo_profiles_disabled`
- `GET /api/v1/context/self`
  - resolves and returns the canonical request context for the current request
  - supports `X-Knowloop-Profile-Id` only in demo-profile mode
  - supports explicit `X-Knowloop-*` context headers through either the legacy or signed adapter, depending on `context_trust_mode`

## 5. Response Envelopes

### 5.1 Success

```json
{
  "request_id": "req-20260408-001",
  "data": {},
  "meta": {}
}
```

Rules:

- `request_id` is always present
- `request_id` belongs to the current HTTP attempt for tracing, even when the route replays a previously accepted mutation result
- `data` contains the primary payload
- `meta` is reserved for pagination or flags

Error envelope rules:

- every error response also includes the same top-level `request_id` shape as a success response
- the error envelope `request_id` is generated by the server for the current HTTP attempt and must match the response `X-Request-Id` header
- the API error payload always has the shape `{ request_id, error: { code, message, details } }` and must not fall back to the framework's top-level `detail` body for `/api/v1/*` routes
- replayed error retries still receive a fresh attempt-local `request_id`; retries never reuse a prior attempt's tracing identifier
- raw `/api/v1/*` `HTTPException` responses that reach the main Knowloop FastAPI app boundary without being converted to `ApiError` still use the same error envelope shape instead of the framework default body
- these generic HTTP fallback guarantees are namespace-wide for published `/api/v1/*` surfaces in this repository; mounted sub-apps or alternate ASGI surfaces must use the same handler stack before they can live under the same API namespace
- route-owned `ApiError` responses define their own machine-readable `error.code`; for statuses not covered by the fallback mappings below, this section guarantees the envelope shape and request-tracing behavior, not a single shared fallback code
- generic HTTP fallback mappings at the main app boundary are:
  - `403` -> `forbidden_scope`
  - `404` -> `not_found`
  - `405` -> `invalid_request`
  - `422` -> `validation_failed`
- other raw HTTP exceptions preserve the common error envelope but use a generic `http_<status_code>` machine code, for example `http_429`; they do not claim a route-owned business semantic
- routes and dependencies that need stable machine-readable API error semantics must raise `ApiError`; generic HTTP fallback handlers guarantee the envelope shape and safe generic codes, but they are not the primary contract surface for route-owned business errors
- authorization, scope, and permission boundaries should raise `ApiError` directly whenever the route needs a more specific distinction than the generic fallback `403 forbidden_scope`
- a syntactically valid but role-disallowed explicit `X-Knowloop-Domain` still fails at the shared request-context validator as `422 validation_failed` before route-family authorization runs

Authorization precedence:

- invalid trusted-context signature, missing signed-context metadata in signed mode, or disabled demo profile usage -> `403` (`untrusted_context` or `demo_profiles_disabled`)
- malformed or missing shared request-context headers, including route families that require an explicit header the shared context cannot infer -> `422` (`missing_context` or `validation_failed`)
- syntactically valid but role-disallowed explicit `X-Knowloop-Domain` override -> `422 validation_failed`
- valid request with the wrong route scope/domain -> `403 forbidden_scope`
- valid request from an unsupported or read-only role -> route-owned `403 forbidden_role` only on route families that explicitly document that distinction, such as `/api/v1/review/*`; other route families may continue to use `403 forbidden_scope` until they publish a narrower role-specific contract

### 5.2 Error

```json
{
  "request_id": "req-20260408-001",
  "error": {
    "code": "duplicate_action",
    "message": "Idempotency-Key was reused for a different query payload within the same scope.",
    "details": {}
  }
}
```

Common error codes:

- `missing_context`
- `validation_failed`
- `invalid_request`
- `http_<status_code>` for unmapped framework HTTP exceptions
- `forbidden_scope`
- `forbidden_role`
- `not_found`
- `duplicate_action`
- `source_integrity_failed`
- `insufficient_verified_context`
- `storage_busy`
- `untrusted_context`
- `demo_profiles_disabled`
- `body_too_large`
- `internal_error`

## 6. Implemented Endpoints

## 6.1 Health and Readiness

### `GET /healthz`

Purpose:

- basic process liveness

### `GET /readyz`
### `GET /api/v1/system/health`
### `GET /api/v1/system/ready`
### `GET /api/v1/system/runtime`

Purpose:

- verifies storage bootstrap and runtime readiness
- exposes the current optional LLM runtime configuration that the API would use for grounded rewrites

## 6.2 Context Bootstrap APIs

### `GET /api/v1/context/profiles`

Purpose:

- expose the checked-in demo/frontend profile registry
- let the frontend switch personas without handcrafting the full `X-Knowloop-*` header bundle

Response highlights:

- `profile_id`
- `label`
- `role`
- `actor_id`
- `course_id`
- `class_id`
- `domain`
- `landing_surface`

### `GET /api/v1/context/self`

Purpose:

- resolve the canonical request context for the current request
- verify whether the request was resolved from `X-Knowloop-Profile-Id` or from explicit `X-Knowloop-*` headers

Response highlights:

- `profile_id`
- `profile_label`
- `role`
- `actor_id`
- `course_id`
- `class_id`
- `domain`
- `domain_was_explicit`

## 6.3 Source APIs

### `POST /api/v1/sources/register`

Purpose:

- register a raw source into manifest-backed storage

Replay behavior:

- `Idempotency-Key` required for safe retry semantics
- same key plus same payload replays safely
- same key plus different payload conflicts

Request body:

```json
{
  "source_type": "lecture_note",
  "title": "Week 03 Chain Rule",
  "content": "# Chain Rule\nUse the outer derivative after the inner derivative.",
  "mime_type": "text/markdown",
  "filename": "week-03-chain-rule.md",
  "tags": ["week-03", "chain-rule"]
}
```

Request field bounds:

- `title`: `1..200` chars after trim
- `content`: `1..64000` chars and non-blank
- `mime_type`: optional, max `100` chars
- `filename`: optional, max `255` chars
- `tags`: max `20` unique non-blank tags after trim/dedupe, each max `40` chars

Response highlights:

- `source_id`
- `source_type`
- `domain`
- `status`
- `stored_path`
- `created_at`

Source ID notes:

- most source IDs are class-scoped
- flexible-domain source types such as `announcement` include an explicit domain token in the durable `source_id`
- title slugs carry a digest suffix to avoid collisions from long or non-ASCII titles
- if the base ID is already used by a different same-title source in the same second, registration appends a short deterministic payload fingerprint before the timestamp instead of rejecting the second source

### `GET /api/v1/sources`

Purpose:

- list registered sources visible in the current scope

Supported query parameters:

- `source_type`
- `q`: optional search query, max `200` chars
- `limit`, `offset`: pagination

Scope notes:

- `course_id`, `class_id`, and `domain` are derived from the request context, not accepted as public query parameters
- requests that include `course_id`, `class_id`, or `domain` query parameters are rejected with `validation_failed`

### `GET /api/v1/sources/{source_id}`

Purpose:

- load one registered source record by ID

## 6.4 Query API

### `POST /api/v1/query/respond`

Purpose:

- retrieve scoped context
- generate an answer
- save the session turn
- emit learning-note or candidate write-back when appropriate

Request body:

```json
{
  "message": "I still do not understand when the chain rule is different from the product rule.",
  "attachment_source_ids": [],
  "allow_raw_source_fallback": true,
  "response_mode": "teaching"
}
```

Request fields:

- `message`: required non-blank string, max `4000` chars after trim
- `attachment_source_ids`: optional list of source IDs, max `10` unique IDs after trim/dedupe, each max `160` chars
- `allow_raw_source_fallback`: whether raw-source fallback is allowed
- `response_mode`: `default`, `concise`, `teaching`, or `review`

Normalization defaults before replay classification:

- omitted `attachment_source_ids` normalizes to `[]`
- omitted `allow_raw_source_fallback` normalizes to `false`
- omitted `response_mode` normalizes to `default`

Allowed roles and domains:

- `student` with `academic`
- `instructor` with `academic`
- `operator` with `operations`
- `validator` with `review`
- `system` is not part of the public query route contract
- when `system` attempts the public query route with a valid review-scoped context, the route returns the route-owned `403 forbidden_role` contract instead of the generic fallback `forbidden_scope`

Response body inside `data`:

```json
{
  "answer": "Use the chain rule when one function is nested inside another...",
  "answer_basis": ["formal_wiki", "session_context"],
  "retrieval_refs": [],
  "writeback_plan": [],
  "session_id": "ses-student-stu-kim-minji-class-calculus-1-2026-spring-a-7df8a1b0c2",
  "created_at": "2026-04-08T11:10:00Z"
}
```

Response `meta.runtime`:

```json
{
  "runtime": {
    "answer_source": "llm_rewrite",
    "stored_answer_source": "deterministic_fallback",
    "llm_enabled": true,
    "llm_applied": true,
    "provider": "openai",
    "configured_model": "gpt-5.4"
  }
}
```

Runtime metadata rules:

- `answer_source` is `llm_rewrite` only when the immediate HTTP response text differs from the deterministic stored session answer
- `stored_answer_source` remains `deterministic_fallback` for the current MVP because replay and session history are always pinned to the deterministic answer
- `llm_enabled` reflects operator configuration, not whether the provider call succeeded
- `llm_applied` reflects whether the provider rewrite actually survived guard checks for the current HTTP attempt
- `provider` and `configured_model` are observability fields only; they do not authorize the provider as a new source of truth

`answer_basis` values currently supported:

- `formal_wiki`
- `session_context`
- `learning_context`
- `raw_source_fallback`

Write-back behavior:

- `session` is always written on success
- `learning_note` may be written for student confusion patterns
- `candidate` may be written for structured review signals
- validator queries stay read-only for learning-note and candidate writes; they persist only the scoped session trace needed for review-safe replay and auditability

Replay behavior:

- if `Idempotency-Key` is supplied, the route treats it as the mutation replay token
- replay ownership is scoped to the normalized query boundary: `role + actor_id + course_id + class_id + domain`
- `Public Query Default Domains v1`:
  - `student` -> `academic`
  - `instructor` -> `academic`
  - `operator` -> `operations`
  - `validator` -> `review`
- for the public query route, omitted `domain` is normalized using `Public Query Default Domains v1` before lookup; this mapping is part of the query contract and must not silently inherit future permission-default changes
- the effective request fingerprint inside that normalized scope is derived from the normalized body fields only: trimmed `message`, sorted+deduplicated `attachment_source_ids`, `allow_raw_source_fallback`, and `response_mode`
- reusing the same `Idempotency-Key` with a different effective request fingerprint in that same normalized scope returns `409 duplicate_action`; if the server can already prove ownership from the pending replay record, this duplicate-action outcome takes precedence even while an earlier same-key mutation is still pending or still recovering durable side effects
- if a same-key retry reaches an already accepted mutation in the same normalized scope, the route replays the stored deterministic `data` payload, including `session_id` and `writeback_plan`, instead of generating a new mutation; the top-level `request_id` still belongs to the current attempt and the retry must not duplicate durable side effects or create a second session record
- when an optional LLM rewrite is enabled, only the first successful HTTP attempt may carry that rewritten `answer`; replay, recovery, and session history stay pinned to the deterministic stored answer
- while the original mutation is still pending or recovering durable side effects, the same normalized replay key may temporarily return `503 storage_busy`
- if a same-key retry sees a fresh pending replay-owner row before the session row exists, the route returns `503 storage_busy` instead of guessing whether the first writer is still alive
- if that pre-session replay-owner row is stale, has no response payload, and its request fingerprint still matches the retry, the route may reclaim the owner internally, create the deterministic session row using the original owner timestamp, and return the normal `200` query response
- if the replay-owner row proves a different request fingerprint, `409 duplicate_action` takes precedence even when the row is stale and the session row does not exist
- `200` replay is allowed only for terminal write-back outcomes; internally cached pending payloads and payloads containing `failed`, `pending`, `in_progress`, `queued`, or non-session `registered` write-backs must be repaired first
- if replay recovery finds a degraded pending owner, an incomplete applied owner, or otherwise cannot safely complete in the current request, the route returns `503 storage_busy` rather than a transient payload conflict or a partial answer
- clients that receive `503 storage_busy` during query replay must retry later with the same `Idempotency-Key`, using backoff; generating a new key turns the retry into a new mutation attempt
- when the server can estimate a safe retry window, it may include `Retry-After`; clients should honor it when present
- `X-Request-Id` remains a tracing header, not the semantic replay key
- durable replay storage, leases, and repair mechanics are internal implementation details described in the storage contracts, not part of this public HTTP contract

Boundary rules:

- students cannot attach raw source IDs directly
- student retrieval refs do not expose raw source metadata
- open candidates are not returned as authoritative student answer evidence

## 6.5 Review Workflow Routes

The review workflow is now implemented through dedicated candidate endpoints.

### 6.5.1 `GET /api/v1/review/candidates`

Purpose:

- list reviewable candidates in the current course/class scope
- default to `status=open`

Allowed roles and domains:

- `instructor` with `academic`
- `operator` with `operations`
- `validator` with `review`
- `system` with `review`

Omitted-domain behavior:

- `instructor` and `operator` may omit `X-Knowloop-Domain` because the shared request-context default resolves to their route-owned review domains
- `validator` may omit `X-Knowloop-Domain` because its shared default also resolves to `review`
- `system` must send `X-Knowloop-Domain: review` explicitly on `/api/v1/review/*`; when it omits the header, the route returns `422 validation_failed` because the route requires an explicit review-domain declaration for system-scoped review access

Authorization notes:

- unsupported roles on review list/detail/patch-preview return route-owned `403 forbidden_role`
- finalize-capable review mutations remain restricted to `instructor` and `validator`; `operator` and `system` receive route-owned `403 forbidden_role`

Shared review input bounds:

- `{candidate_id}` path values and `target_candidate_id` fields are max `160` chars
- `target_page_id` is max `120` chars
- `target_path` is max `320` chars
- `notes`, `approval_notes`, `merge_notes`, `drop_notes`, and `resume_notes` are each max `1000` chars

Query parameters:

- `status`: optional `open`, `promoted`, `merged`, `dropped`
- `kind`: optional candidate kind
- `limit`, `offset`: pagination

Response body inside `data`:

- candidate summaries derived from `CandidateItem`
- each item includes `review_domain`

### 6.5.2 `GET /api/v1/review/candidates/{candidate_id}`

Purpose:

- load one review candidate with audit history

Response body inside `data`:

- `candidate`
- `audit_events` including structured `details` when an audit action carries machine-readable metadata
- `available_actions`
  - open academic candidates: `patch_preview`, `approve`, `merge`, `drop`
  - operations candidates visible to `operator`: `patch_preview`
  - promoted candidates with `wiki_sync_status = pending`: `resume_sync` for finalize-capable roles
  - `system` remains read-only in the review workflow, so it only receives `patch_preview`, including when a promoted candidate is still pending wiki sync

### 6.5.3 `POST /api/v1/review/candidates/{candidate_id}/patch-preview`

Purpose:

- generate the wiki patch preview without mutating candidate status

Request body:

```json
{
  "target_page_id": "page-faq-homework-submission",
  "target_path": "data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
  "notes": "Optional preview notes."
}
```

Response body inside `data`:

- `candidate`
- `patch`
- `before_markdown`
- `after_markdown`

Rules:

- preview is read-only
- preview does not require `Idempotency-Key`
- preview must still satisfy role and scope boundaries
- `operator` may use preview for operations-domain candidates but remains read-only for review mutations
- `system` may inspect review candidates and generate patch previews, but it may not finalize `approve`, `merge`, `drop`, or `resume-sync`
- when `target_page_id` already exists, it must belong to the same `course_id` and `class_id` scope as the candidate being reviewed

### 6.5.4 `POST /api/v1/review/candidates/{candidate_id}/approve`

Purpose:

- promote an open candidate into formal wiki through the dedicated review workflow

Request body:

```json
{
  "target_page_id": "page-faq-homework-submission",
  "target_path": "data/wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
  "approval_notes": "Promote to shared FAQ for the course wiki."
}
```

Rules:

- requires `Idempotency-Key`
- `instructor` may approve academic candidates
- `operator` is read-only in the MVP review flow and cannot approve, merge, or drop candidates
- `validator` may approve through review-scoped requests
- `system` is read-only in the review workflow and cannot approve candidates
- replay identity for review mutations is derived from the normalized mutation payload and scope, never from transport-only `X-Request-Id`; same-key retries may change `X-Client-Request-Id` without changing replay ownership
- `target_path` must match the canonical wiki path for `target_page_id`
- `target_page_id` must use the strict `page-<domain>-<slug>` contract, where `<slug>` contains only lowercase letters, digits, and hyphens
- when `target_page_id` already exists, it must belong to the same `course_id` and `class_id` scope as the candidate being reviewed
- before any candidate is promoted or wiki mutation is written, every source id that would remain in final wiki `source_refs` must pass source-integrity preflight: the manifest record exists, the source belongs to the same course/class and review domain, candidate-owned refs match the manifest `source_type`, and the backing raw-source file is readable with the manifest checksum
- source-integrity preflight failures return `422 source_integrity_failed` with `details.candidate_id`, `details.source_id`, `details.ref_owner`, and `details.reason`
- `details.ref_owner` is `candidate` for refs owned by the approving candidate and `wiki_page` for existing refs carried forward from the target wiki page
- `details.reason` is one of `source_ref_unresolved`, `source_file_path_invalid`, `source_file_missing`, `source_file_unreadable`, `source_scope_mismatch`, `source_domain_mismatch`, `source_type_mismatch`, or `source_checksum_mismatch`
- fresh approve source-integrity failures happen before replay-owner state, candidate transition audit, or wiki write-back is created
- candidate and wiki file locks older than 5 minutes are treated as crash leftovers and may be reclaimed before the approval write continues
- active candidate or wiki file locks return `503 storage_busy`; callers should retry later with the same `Idempotency-Key`
- successful approval promotes the candidate first with `candidate.wiki_sync_status = pending`, emits a `candidate_wiki_sync_pending` audit marker, then applies a deterministic wiki patch, marks the candidate `wiki_sync_status = synced`, and closes with `candidate_wiki_synced`
- same `Idempotency-Key` plus the same approval payload replays safely
- approval replay still reruns source-integrity preflight before any wiki rewrite; if raw evidence drifted after the original success, replay returns `422 source_integrity_failed` instead of writing unverified metadata
- the approval replay contract includes a frozen patch plan fingerprint; if the candidate or wiki page drifts enough to change that plan, the retry must return `409 duplicate_action`
- if an existing `target_page_id` drifts into another scope after a partial approval, the replay still counts as frozen-plan drift and must return `409 duplicate_action`
- replay comparison normalizes the canonical wiki target, so omitting `target_path` or providing the canonical path replays safely
- same `Idempotency-Key` plus a different effective approval payload returns `409 duplicate_action`
- retry after a partial wiki-sync failure must converge to one promoted candidate state and one final wiki patch audit chain
- a failed approve attempt may still leave `candidate.status = promoted` with `wiki_sync_status = pending`; callers may retry with the same `Idempotency-Key`, or they may use the dedicated `resume-sync` endpoint to continue the stored promotion attempt with a fresh request key
- internal persistence or I/O partial failures that are not represented as validation, frozen-plan drift, source-integrity, duplicate-action, or storage-lock errors currently surface as `500 internal_error` until the original idempotent approval either converges or is explicitly superseded
- the wiki-sync audit chain carries structured `details` for `candidate_wiki_sync_pending`, `wiki_patch_applied`, and `candidate_wiki_synced` with `candidate_id`, `promotion_attempt_id`, and `approval_plan_fingerprint`; retries must converge onto one chain instead of creating a second attempt identity

Response body inside `data`:

- `candidate`
- `patch`
- `wiki_page`

### 6.5.5 `POST /api/v1/review/candidates/{candidate_id}/resume-sync`

Purpose:

- continue a previously promoted candidate whose wiki sync stopped after the approval plan was frozen

Request body:

```json
{
  "resume_notes": "Resume the stored approval plan after a transient failure."
}
```

Contract:

- requires `Idempotency-Key`
- `instructor` may resume academic candidates in scope
- `validator` may resume review-scoped candidates
- `operator` remains read-only in the MVP review flow and cannot resume wiki sync
- `system` remains read-only in the review workflow and cannot resume wiki sync
- candidate must already be `status = promoted` and `wiki_sync_status = pending`
- the server reuses the stored `promotion_attempt_id` and stored `approval_plan_fingerprint`; the canonical `wiki_sync_target_path` remains candidate-owned state and must still validate against the pending plan during resume
- resume-sync reruns the source-integrity preflight against the final wiki `source_refs` set before applying the pending wiki mutation; failures return `422 source_integrity_failed`
- candidate and wiki file locks older than 5 minutes are treated as crash leftovers and may be reclaimed; active lock contention returns `503 storage_busy`
- resume continues the existing pending promotion attempt and must not emit a second `candidate_wiki_sync_pending` audit event
- if a pending attempt has no `wiki_patch_applied` or `candidate_wiki_synced` audit yet, same-scope wiki body drift may be recovered by refreshing the stored `approval_plan_fingerprint` and updating the single pending audit details before applying the current patch plan
- after any wiki patch or synced marker exists for the promotion attempt, the current candidate and wiki page must still match the frozen approval plan; if that plan drifts, the request returns `409 duplicate_action`
- if the stored target page drifts into another scope before resume, that still counts as frozen-plan drift and must return `409 duplicate_action`
- unlike `approve`, `resume-sync` may use a fresh `Idempotency-Key` because it resumes a server-owned promotion attempt rather than creating a new approval plan
- a fresh `resume-sync` key that fails frozen-plan validation, scope validation, or cross-course validation must not persist a new replay-owner mutation record for that rejected attempt
- once a `resume-sync` request succeeds, reusing the same `Idempotency-Key` with the same payload must replay the stored success response, even if the original request crashed after syncing the wiki/candidate but before the mutation request was marked applied
- once a `resume-sync` owner row stores a success payload, replay verification must rely on the server-owned resume contract frozen in that replay record rather than on mutable candidate metadata alone
- the replay record may persist that frozen resume contract in an internal `_resume_contract` storage field even though the public HTTP `data` payload remains unchanged
- reusing the same `Idempotency-Key` with different `resume_notes` must return `409 duplicate_action`
- resume recovery may accept legacy pre-details wiki-sync audit rows only when the relevant `entity_type + entity_id + action` chain is otherwise unique; any newly persisted wiki-sync audit event must include the structured `details` contract described above
- page-owned `wiki_patch_applied` legacy rows are preserved when the same frozen promotion attempt cannot be proven from the existing row, so replay may append a new structured page audit event instead of mutating the historical one

Response body inside `data`:

- `candidate`
- `patch`
- `wiki_page`
  - `updated_at` means the actual wiki sync completion time, not the original approval time

The `candidate` payload should include `wiki_sync_status` and, once sync is complete, `wiki_synced_at`.

### 6.5.6 `POST /api/v1/review/candidates/{candidate_id}/merge`

Purpose:

- merge a duplicate open candidate into an active target candidate

Request body:

```json
{
  "target_candidate_id": "cand-misconception-class-calculus-1-2026-spring-a-chain-rule-product-rule-mixup-20260408T112000Z",
  "merge_notes": "Merge duplicate misconception into the stronger canonical candidate."
}
```

Rules:

- requires `Idempotency-Key`
- target candidate must remain active
- merge stays inside the same course/class scope
- `operator` is not allowed to merge candidates in the MVP review flow
- `system` is not allowed to merge candidates in the MVP review flow
- candidate file locks older than 5 minutes are treated as crash leftovers and may be reclaimed; active lock contention returns `503 storage_busy`
- merge replay identity is anchored to the original target candidate meaning, not only its ID; `title`, `summary`, and `related_page_id` drift make the replay a different request
- same `Idempotency-Key` plus the same merge payload replays safely
- same `Idempotency-Key` plus a different merge payload returns `409 duplicate_action`

### 6.5.7 `POST /api/v1/review/candidates/{candidate_id}/drop`

Purpose:

- mark an open candidate as dropped without deleting its history

Request body:

```json
{
  "reason": "insufficient_shared_value",
  "drop_notes": "Keep the question in audit history until stronger evidence appears."
}
```

Allowed `reason` values:

- `insufficient_shared_value`
- `obsolete_operations_signal`
- `superseded_by_existing_candidate`

Rules:

- requires `Idempotency-Key`
- drop is a status transition, not a delete
- `operator` is not allowed to drop candidates in the MVP review flow
- `system` is not allowed to drop candidates in the MVP review flow
- candidate file locks older than 5 minutes are treated as crash leftovers and may be reclaimed; active lock contention returns `503 storage_busy`
- the drop audit record must preserve `reason` as structured metadata as well as human-readable notes
- same `Idempotency-Key` plus the same drop payload replays safely
- same `Idempotency-Key` plus a different drop payload returns `409 duplicate_action`

## 6.6 Wiki Read Routes

The formal wiki browser is now implemented through dedicated read-only endpoints.

### 6.5.1 `GET /api/v1/wiki/pages`

Purpose:

- list visible formal wiki pages in the current course/class scope
- support scoped search across the formal wiki browser

Allowed roles and domains:

- `student` with `academic`
- `instructor` with `academic`
- `operator` with `operations`
- `validator` with `review` or an explicit narrow domain (`academic` or `operations`)
- `system` with omitted domain or `review` for full visibility, or an explicit narrow domain (`academic` or `operations`)

Query parameters:

- `q`: optional search query
- `limit`, `offset`: pagination

Rules:

- `student` and `instructor` can only browse academic wiki domains
- `operator` can only browse operations wiki pages
- `validator` and `system` may browse both academic and operations pages from `review`, or narrow themselves with an explicit domain
- results are always constrained to the current `course_id` and `class_id`

Response body inside `data`:

- `page_id`
- `domain`
- `title`
- `summary`
- `updated_at`

### 6.5.2 `GET /api/v1/wiki/pages/{page_id}`

Purpose:

- load one visible wiki page by ID

Rules:

- page visibility still respects role/domain boundaries
- callers cannot cross course/class scope by guessing page IDs
- canonical wiki storage is class-scoped under `data/wiki/<domain>/<class-id>/...`
- noncanonical, unreadable, or otherwise invalid wiki files stay out of the normal wiki browser and are surfaced through maintenance as repair-required layout issues
- unreadable legacy unscoped files only surface through scoped maintenance when `class_scope` metadata still survives and matches the current scope

Response body inside `data`:

- `page_id`
- `domain`
- `title`
- `summary`
- `course_id`
- `class_scope`
- `updated_at`
- `source_refs`
- `candidate_refs`
- `body_markdown`

## 6.7 Instructor Insight Routes

The instructor dashboard is implemented through aggregated, academic-only insight endpoints.

### 6.6.1 `GET /api/v1/instructor/insights/overview`

Purpose:

- provide a class-level overview for instructors without exposing raw student transcript bodies

Allowed roles and domains:

- `instructor` with `academic`

Rules:

- response is aggregate-first and does not expose raw student question text
- insight data is limited to academic student sessions, academic candidates, and learning-note aggregates within the current course/class scope
- operations-domain sessions and operations candidates are excluded from the instructor surface
- session-derived counts and topic summaries are computed from all scoped academic student session metadata, not from a recent-session display window

Response body inside `data`:

- `course_id`
- `class_id`
- `student_session_count`
- `unique_student_count`
- `open_candidate_total`
- `candidate_counts`
- `students_with_learning_notes`
- `students_with_open_gaps`
- `top_topics`
- `top_gap_clusters`
- `top_patterns`

### 6.6.2 `GET /api/v1/instructor/insights/patterns`

Purpose:

- list aggregated candidate patterns for the instructor dashboard

Allowed roles and domains:

- `instructor` with `academic`

Query parameters:

- `kind`: optional academic candidate kind filter
- `limit`, `offset`: pagination

Rules:

- patterns group related open academic candidates instead of returning the review inbox shape directly
- pattern pagination is applied after grouping all visible scoped academic candidates, and candidate `session_refs` resolve against the full scoped academic student-session metadata set

Response body inside `data`:

- `pattern_id`
- `kind`
- `title`
- `summary`
- `related_page_id`
- `candidate_count`
- `session_count`
- `student_count`
- `latest_created_at`
- `candidate_ids`
- `tags`
- `max_confidence`

## 6.8 Session Search Routes

The session browser is implemented as a role-aware search surface with redaction rules.

### 6.7.1 `GET /api/v1/sessions/search`

Purpose:

- search durable session history inside the caller's allowed scope

Allowed roles and domains:

- `student` with `academic`
- `instructor` with `academic`
- `operator` with `operations`

Query parameters:

- `q`: required non-blank search query
- `limit`, `offset`: pagination

Rules:

- `student` searches only their own session history and receives question/answer previews
- `operator` searches only their own operations-domain session history and receives previews
- `instructor` searches class-scoped student sessions but receives redacted hits without raw transcript previews
- `validator` and `system` do not use this route family in the MVP

Response body inside `data`:

- `session_id`
- `role`
- `created_at`
- `tags`
- `candidate_ref_count`
- `learning_note_ref_count`
- `source_ref_count`
- `visibility`
- `match_summary`
- `question_preview`
- `answer_preview`

### 6.7.2 `GET /api/v1/sessions/recent`

Purpose:

- list recent session hits inside the same role-aware scope as session search

Allowed roles and domains:

- `student` with `academic`
- `instructor` with `academic`
- `operator` with `operations`

Rules:

- shares the same redaction rules as `GET /api/v1/sessions/search`
- acts as the default recent-history surface when no search query is provided

## 6.9 Maintenance Routes

The maintenance surface is implemented through a dedicated report generator and a read-only status endpoint.

### 6.8.1 `GET /api/v1/maintenance/report`

Purpose:

- generate the current maintenance report for stale candidates and orphan wiki references
- persist the scoped report to `data/meta/maintenance/{course_id}/{class_id}/lint-status.json`

Allowed roles and domains:

- `validator` with `review`
- `system` with `review`

Rules:

- this route is operational and read-model producing, so it is restricted to review-scoped maintenance owners
- stale open candidates whose `updated_at` is older than the configured threshold are returned as warnings
- orphan `candidate_refs` and source references whose manifest row or backing source file is no longer available are returned as errors
- noncanonical, unreadable, or metadata-invalid wiki files in the current scope are returned as errors so legacy wiki storage drift cannot stay hidden
- a wiki file that physically lives under the current class-scoped path but whose frontmatter points to another scope is treated as metadata-invalid and surfaced for repair
- unreadable legacy unscoped files only appear when the remaining frontmatter still contains a matching `class_scope`, and any surviving `course_id` also matches the requested course; `course_id`-only or completely unattributable legacy files are left out of scoped reports to avoid cross-class leakage
- report ordering is deterministic so persisted maintenance output stays diff-friendly

Response body inside `data`:

- `version`
- `course_id`
- `class_id`
- `status`
- `last_run_at`
- `health_score`
- `review_queue_count`
- `summary`
- `checks`

### 6.8.2 `GET /api/v1/maintenance/status`

Purpose:

- load the latest persisted maintenance report without recomputing it

Allowed roles and domains:

- `instructor` with `academic`
- `validator` with `review`
- `system` with `review`

Rules:

- this route is read-only and does not generate a report when none exists yet
- when no report has been generated, the route returns a default `not-run` payload
- instructors may inspect maintenance health for course operations, but they cannot trigger report generation
- maintenance status is a summary surface and does not expose raw session question bodies
- the returned status is always scoped to the requested `course_id` and `class_id`
- if a persisted report file is unreadable or its embedded scope does not match the requested path scope, the route returns an `error` payload for the requested scope with a `maintenance_report_unreadable` check
- `validator` and `system` receive the full `checks` payload with `entity_id` and `details`
- `instructor` receives a redacted `checks` payload that keeps `code`, `severity`, `entity_type`, and a stable public `summary` only
- `last_run_at` is omitted when no report has been generated yet, or when a persisted report exists but its timestamp metadata is unreadable, because the status payload excludes null fields

Response body inside `data`:

- `version`
- `course_id`
- `class_id`
- `status`
- `last_run_at` when the persisted report includes a readable timestamp
- `health_score`
- `review_queue_count`
- `summary`
- `checks`

## 7. Planned but Not Yet Implemented

The following workflow surfaces remain planned next:

- runbook and handoff expectations

## 8. Status Codes

Current route behavior uses these status classes:

- `200 OK`: successful read or query workflow
- `201 Created`: successful source registration
- `400 Bad Request`: request violates a workflow rule
- `403 Forbidden`: request crosses a protected scope boundary
- `404 Not Found`: requested entity is missing
- `409 Conflict`: contract conflict such as duplicate mutation key or insufficient verified context
- `422 Unprocessable Entity`: request context or payload validation failed
- `503 Service Unavailable`: storage lock or temporary persistence contention

## 9. Contract Maintenance

Any backend change that modifies:

- headers
- envelope shapes
- route paths
- idempotency behavior
- `answer_basis` values

must update this document, the relevant tests, and any fixture expectations in the same change set.
