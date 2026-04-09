# Knowloop Query / Write-back Policy

## 1. Purpose

This document defines how `POST /api/v1/query/respond` retrieves context, generates answers, and writes durable artifacts back into the Knowloop memory layers.

It bridges four other contracts:

- `docs/product/mvp-scope.md`
- `docs/architecture/data-contracts.md`
- `docs/architecture/promotion-policy.md`
- `docs/product/role-permissions.md`

## 2. Core Policy

1. Formal wiki is the primary answer basis.
2. Session memory is support context, not shared truth.
3. Learning notes are personal learning-state hints, not public facts.
4. Raw sources are fallback evidence, not the default answer layer.
5. Open candidates are write-back outputs, not authoritative answer inputs for student queries.
6. Query and write-back are related but separate steps.
   The answer is generated first. Then the system decides what should be stored.

## 3. Scope Resolution

Every query is resolved inside this scope:

- `role`
- `actor_id`
- `course_id`
- `class_id`
- `domain`

Role defaults:

- `student` -> `academic`
- `instructor` -> `academic`
- `operator` -> `operations`
- `validator` -> `review`

If the request context does not satisfy role and domain rules, the query must fail before retrieval begins.

## 4. Retrieval Priority

## 4.1 Shared Order

The MVP retrieval order is:

1. resolve scope and permissions
2. inspect recent same-user session history in the same class
3. search formal wiki pages in the current course and domain
4. load student learning context when allowed
5. fall back to raw sources only when the request explicitly allows it and wiki coverage is insufficient
6. generate the answer
7. compute write-back actions

## 4.2 Formal Wiki

Formal wiki is the default answer layer.

Rules:

- query first searches wiki pages that match `course_id`, `class_id`, and allowed domains
- if wiki coverage is strong enough, the answer should be grounded in wiki alone
- wiki retrieval refs may expose `source_refs` to non-student roles
- student responses may reference the wiki page, but do not expose raw source metadata directly

## 4.3 Session Context

Session context exists to make follow-up answers coherent.

Rules:

- only same-user, same-class, same-course session history is used for student context
- current-session replay must not re-ingest its own stored session as context
- session context can justify `session_context` in `answer_basis`
- session context does not override formal wiki

## 4.4 Learning Context

Learning context is student-only retrieval support.

Rules:

- only `student` queries can read a learning note
- a learning note may contribute `learning_context` when it already existed before the current query turn
- a learning note created by the current query does not retroactively count as answer evidence for that same turn
- learning context may personalize wording and next-step guidance
- learning context must not be treated as verified public knowledge

## 4.5 Raw Source Fallback

Raw source fallback is allowed only when all of the following are true:

- the request explicitly sets `allow_raw_source_fallback=true`
- the query stays inside the caller's role and domain boundary
- the formal wiki does not fully cover the question, or the caller is in an allowed non-student workflow that can inspect sources

Student-specific restrictions:

- students cannot attach raw source IDs directly
- student-facing retrieval refs do not expose raw source entities or `source_refs`

## 4.6 Candidate Visibility

Open candidates are not authoritative answer material for student queries.

Role behavior:

- `student`: does not retrieve open candidates as evidence
- `instructor`: may inspect candidate patterns in dedicated review or dashboard flows
- `operator`: only sees operations-domain candidate material
- `validator`: may inspect candidate, source, and audit detail for promotion work

## 5. Answer Basis Contract

`answer_basis` may contain the following ordered values:

- `formal_wiki`
- `session_context`
- `learning_context`
- `raw_source_fallback`

Rules:

- order matters and reflects the retrieval stack used for the response
- `learning_context` only appears when a pre-existing learning note influenced the response
- `raw_source_fallback` only appears when raw-source evidence materially contributed to the answer

## 6. Write-back Rules

## 6.1 Session Write

Every successful query writes a session record.

Required behavior:

- save the durable question-answer turn first
- attach retrieval refs used for the answer
- attach `candidate_refs` and `learning_note_refs` after downstream writes succeed

If downstream linking fails after the session itself is saved, the answer should still return successfully and the system must emit an audit event.

## 6.2 Learning Note Write

Learning notes are written when the query signals a real student learning gap.

Current MVP rule:

- student confusion patterns such as chain-rule vs product-rule misunderstanding generate or update a learning note

Expected content:

- `concepts`
- `gaps`
- `next_actions`
- `source_refs`
- `session_refs`

## 6.3 Candidate Write

Candidates are written when the query produces a structured signal worth later review.

Current MVP examples:

- `misconception`
- `unresolved_question`
- `operations_note`
- `faq` for instructor or validator workflows

Rules:

- candidate `session_refs` may include supporting same-user or class-aggregated sessions used for write-back evidence
- this does not mean those supporting sessions must appear in `retrieval_refs` for the answer itself
- instructor FAQ candidates may stay answer-grounded in formal wiki while still linking repeated class sessions for later review

Student homework questions that are already fully covered by formal wiki remain session-only in the MVP. They should not create FAQ candidates automatically.

## 6.4 Failure Handling

Write-back is best-effort after the session answer is generated.

Rules:

- session save failure is fatal for the request
- learning write-back failure returns success for the query but emits `learning_writeback_failed`
- candidate write-back failure returns success for the query but emits `candidate_writeback_failed`
- session artifact-link failure returns success for the query but emits `session_artifact_link_failed`

## 7. Idempotency and Replay

`POST /api/v1/query/respond` supports safe replay when `Idempotency-Key` is provided.

Rules:

- the same `Idempotency-Key` plus the same scoped payload must resolve to the same session mutation
- reusing the same `Idempotency-Key` with a different payload in the same scope must fail with a conflict
- ordinary requests without `Idempotency-Key` still create normal per-turn session records

This keeps retries safe without turning `X-Request-Id` into the semantic source of truth for mutation replay.

## 8. Role-Specific Summary

### 8.1 Student

Retrieval order:

1. formal wiki
2. own recent session history
3. own pre-existing learning note
4. allowed raw fallback

Write-back:

- always session
- learning note when confusion markers are detected
- candidate only for allowed structured signals such as misconception or unresolved question

### 8.2 Instructor

Retrieval order:

1. formal wiki
2. aggregated student session patterns for the class when needed
3. raw source fallback when allowed

Write-back:

- session
- instructor-facing FAQ candidate signals when appropriate

### 8.3 Operator

Retrieval order:

1. operations wiki
2. operator session history
3. operations raw sources when allowed

Write-back:

- session
- operations candidates only

### 8.4 Validator

Retrieval order:

1. review-safe wiki and candidate context
2. supporting source and audit traces in review workflows

Write-back:

- not through the student query path
- validator promotion actions belong to dedicated review endpoints

### 8.5 Dedicated Review Endpoints

Candidate promotion, merge, drop, and wiki patch preview live outside the query path.

Workflow boundary rules:

- `instructor` performs academic review actions with `X-Knowloop-Domain: academic`
- `operator` performs read-only operations review actions (`list`, `detail`, `patch-preview`) with `X-Knowloop-Domain: operations`
- `validator` and `system` perform dedicated review actions with `X-Knowloop-Domain: review`
- the `/review/*` route family, not the domain header by itself, is what unlocks promotion actions
- query routes must never inherit these review-only mutations implicitly

## 9. Non-goals

The query path must not:

- directly mutate formal wiki pages
- expose another student's private session content to students
- treat open candidates as formal truth for student answers
- promote candidate material without a separate review action

## 10. Change Control

If answer-basis values, replay semantics, or write-back behavior changes, this document, the API contract, the relevant fixtures, and the query tests must be updated together.
