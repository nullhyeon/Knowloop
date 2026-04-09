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
- dedicated review endpoints still use role-specific domain ownership:
  - `instructor` review requests use `academic`
  - `operator` review requests use `operations`
  - `validator` and `system` review requests use `review`
- `/api/v1/review/*` is the workflow boundary for candidate promotion actions; `X-Knowloop-Domain` alone does not grant review authority.

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

## 6.4 Review Workflow Routes

The review workflow is now implemented through dedicated candidate endpoints.

### 7.1 `GET /api/v1/review/candidates`

Purpose:

- list reviewable candidates in the current course/class scope
- default to `status=open`

Allowed roles and domains:

- `instructor` with `academic`
- `operator` with `operations`
- `validator` with `review`
- `system` with `review`

Query parameters:

- `status`: optional `open`, `promoted`, `merged`, `dropped`
- `kind`: optional candidate kind
- `limit`, `offset`: pagination

Response body inside `data`:

- candidate summaries derived from `CandidateItem`
- each item includes `review_domain`

### 7.2 `GET /api/v1/review/candidates/{candidate_id}`

Purpose:

- load one review candidate with audit history

Response body inside `data`:

- `candidate`
- `audit_events`
- `available_actions`

### 7.3 `POST /api/v1/review/candidates/{candidate_id}/patch-preview`

Purpose:

- generate the wiki patch preview without mutating candidate status

Request body:

```json
{
  "target_page_id": "page-faq-homework-submission",
  "target_path": "data/wiki/faq/homework-submission.md",
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

### 7.4 `POST /api/v1/review/candidates/{candidate_id}/approve`

Purpose:

- promote an open candidate into formal wiki through the dedicated review workflow

Request body:

```json
{
  "target_page_id": "page-faq-homework-submission",
  "target_path": "data/wiki/faq/homework-submission.md",
  "approval_notes": "Promote to shared FAQ for the course wiki."
}
```

Rules:

- requires `Idempotency-Key`
- `instructor` may approve academic candidates
- `operator` is read-only in the MVP review flow and cannot approve, merge, or drop candidates
- `validator` may approve through review-scoped requests
- `target_path` must match the canonical wiki path for `target_page_id`
- successful approval promotes the candidate first, emits a `candidate_wiki_sync_pending` audit marker, then applies a deterministic wiki patch and closes with `candidate_wiki_synced`

Response body inside `data`:

- `candidate`
- `patch`
- `wiki_page`

### 7.5 `POST /api/v1/review/candidates/{candidate_id}/merge`

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

### 7.6 `POST /api/v1/review/candidates/{candidate_id}/drop`

Purpose:

- mark an open candidate as dropped without deleting its history

Request body:

```json
{
  "reason": "insufficient_shared_value",
  "drop_notes": "Keep the question in audit history until stronger evidence appears."
}
```

Rules:

- requires `Idempotency-Key`
- drop is a status transition, not a delete
- `operator` is not allowed to drop candidates in the MVP review flow

## 6.5 Wiki Read Routes

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

## 6.6 Instructor Insight Routes

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
- response may include candidate IDs for drill-down into the dedicated review workflow, but not raw session question bodies

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

## 7. Planned but Not Yet Implemented

The following workflow surfaces remain planned next:

- session search endpoints
- maintenance and stale-detection outputs

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
