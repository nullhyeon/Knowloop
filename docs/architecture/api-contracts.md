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

## 4. Request Context Headers

All non-system routes use request context headers.

Required headers:

- `X-Knowloop-Role`
- `X-Knowloop-Actor-Id`
- `X-Knowloop-Course-Id`
- `X-Knowloop-Class-Id`

Optional headers:

- `X-Knowloop-Domain`
- `X-Request-Id`
- `Idempotency-Key`

Header notes:

- `X-Request-Id` is echoed back for tracing.
- `Idempotency-Key` is the replay-safe mutation key for routes that support retry semantics.
- role and domain combinations must satisfy the role-permission contract.

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
- `data` contains the primary payload
- `meta` is reserved for pagination or flags

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
- `forbidden_scope`
- `forbidden_role`
- `not_found`
- `duplicate_action`
- `insufficient_verified_context`
- `storage_busy`
- `internal_error`

## 6. Implemented Endpoints

## 6.1 Health and Readiness

### `GET /healthz`

Purpose:

- basic process liveness

### `GET /readyz`
### `GET /api/v1/system/health`
### `GET /api/v1/system/ready`

Purpose:

- verifies storage bootstrap and runtime readiness

## 6.2 Source APIs

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

### `GET /api/v1/sources`

Purpose:

- list registered sources visible in the current scope

Supported filters:

- `course_id`
- `class_id`
- `domain`
- `source_type`

### `GET /api/v1/sources/{source_id}`

Purpose:

- load one registered source record by ID

## 6.3 Query API

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

- `message`: required non-blank string
- `attachment_source_ids`: optional list of source IDs
- `allow_raw_source_fallback`: whether raw-source fallback is allowed
- `response_mode`: `default`, `concise`, `teaching`, or `review`

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

`answer_basis` values currently supported:

- `formal_wiki`
- `session_context`
- `learning_context`
- `raw_source_fallback`

Write-back behavior:

- `session` is always written on success
- `learning_note` may be written for student confusion patterns
- `candidate` may be written for structured review signals

Replay behavior:

- if `Idempotency-Key` is supplied, the route treats it as the mutation replay token
- reusing the same `Idempotency-Key` with a different scoped payload returns `409 duplicate_action`
- `X-Request-Id` remains a tracing header, not the semantic replay key

Boundary rules:

- students cannot attach raw source IDs directly
- student retrieval refs do not expose raw source metadata
- open candidates are not returned as authoritative student answer evidence

## 7. Planned but Not Yet Implemented

The following workflow surfaces are planned next, but are not part of the implemented HTTP surface yet:

- review candidate actions such as approve, merge, drop, and patch preview
- dedicated wiki listing and detail endpoints
- instructor insight endpoints

These remain locked at the document level, but should not be presented as already implemented runtime behavior.

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
