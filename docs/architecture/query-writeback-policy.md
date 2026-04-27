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
6. If an optional LLM rewrite is enabled, it may decorate the immediate HTTP response only.
   The stored session answer and replay-authoritative answer remain deterministic.
6. Query and write-back are related but separate steps.
   The answer is generated first. Then the system decides what should be stored.

## 3. Scope Resolution

Every query is resolved inside this scope:

- `role`
- `actor_id`
- `course_id`
- `class_id`
- `domain`

Public query roles:

- `student`
- `instructor`
- `operator`
- `validator`

The public `POST /api/v1/query/respond` contract does not expose a `system` caller role.

If the request context does not satisfy role and domain rules, the query must fail before retrieval begins.
If `domain` is omitted, the server must normalize it using `Public Query Default Domains v1` before any permission or replay-ownership lookup.

`Public Query Default Domains v1`:

- `student` -> `academic`
- `instructor` -> `academic`
- `operator` -> `operations`
- `validator` -> `review`

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
- session artifact-link failure returns success for the query but emits `session_artifact_link_failed`, including replay-time repair attempts

## 7. Idempotency and Replay

`POST /api/v1/query/respond` supports safe replay when `Idempotency-Key` is provided.

Rules:

- the same `Idempotency-Key` plus the same scoped payload must resolve to the same session mutation
- that replay scope uses the normalized query boundary: `role + actor_id + course_id + class_id + domain`
- omitted query body fields normalize before fingerprinting: `attachment_source_ids -> []`, `allow_raw_source_fallback -> false`, `response_mode -> default`
- the effective request fingerprint inside that scope is derived from the normalized body contract: trimmed `message`, sorted+deduplicated `attachment_source_ids`, `allow_raw_source_fallback`, and `response_mode`
- the replay-owner record lives in `mutation_requests`; for query mutations it uses the deterministic replay-owned `session_id` plus the effective request fingerprint to classify same-key retries before the expensive work finishes
- once a query mutation succeeds, later same-key retries replay the stored response shape instead of regenerating a fresh retrieval plan from newer history
- replay preserves the stored deterministic `data` payload and write-back outcome; the outer HTTP `request_id` remains attempt-local tracing metadata and is server-owned for that attempt
- when an optional LLM rewrite decorates the first successful HTTP response, replay and recovery still use the deterministic stored answer from the session row
- if two identical same-key requests race, the losing request must recover the stored session/result instead of surfacing a false payload-conflict error
- if a same-key race is still actively progressing, the retry may briefly wait for the winner's stored replay payload before taking over recovery work
- if a retry finds a fresh pending replay-owner row before the session row exists, it must return `503 storage_busy`; the server cannot yet distinguish active work from a crash without waiting for the lease to expire
- if a retry finds a stale pending replay-owner row before the session row exists, and the row has no response payload and the same effective request fingerprint, it may reclaim that owner row and continue the original deterministic session mutation using the owner row's original timestamp
- if that owner row proves a different effective request fingerprint, `409 duplicate_action` takes precedence whether or not the owner row is stale
- if a retry lands while the original request has only persisted the session row, the retry must finish the pending learning/candidate write-backs before caching the replay response
- a session row that already exists while the replay-owner record is still `pending` is still visible to normal read surfaces inside the caller's role boundary, but replay acceptance is not considered complete until the matching `mutation_requests` row reaches `applied`
- `mutation_requests.response_json` on a `pending` owner is an internal recovery cache, not an externally replayable success payload
- successful replay may return `200` only when the owner is `applied` and the recovered durable response has terminal write-back statuses: session row saved, learning note `updated`, and candidate `open` or `updated`
- `failed`, `pending`, `in_progress`, `queued`, and non-session `registered` write-back statuses are incomplete for replay; retries must repair them or return `503 storage_busy`
- if an `applied` owner is found with an incomplete durable response, the server must repair the write-backs before replay; if repair still cannot complete, the owner is treated as pending recovery and the retry returns `503 storage_busy`
- pending replay ownership uses a bounded internal lease backed by `mutation_requests.updated_at`; active work refreshes that timestamp and retries may reclaim recovery only after that lease expires
- if the stored replay payload still cannot be recovered after bounded recovery work, the route must return `503 storage_busy` instead of a transient payload-conflict response or a partially reconstructed answer
- reusing the same `Idempotency-Key` with a different effective request fingerprint in the same scope must fail with a conflict; if pending ownership is already provable from the replay-owner record, this `duplicate_action` outcome takes precedence even before the earlier mutation reaches `applied`
- if the server cannot yet prove same-key ownership from the pending replay-owner record, it must return `503 storage_busy` instead of guessing between `duplicate_action` and safe replay
- when the server can estimate a safe retry window for `storage_busy`, it should expose that via `Retry-After`
- rejected query requests must not create durable `mutation_requests` rows; idempotency state begins only once the request passes scope and verified-context gates
- replay must preserve the original answer basis; if the first successful attempt used a pre-existing learning note, the replay must still emit the same `learning_context` evidence instead of dropping it because the session was later appended to that note
- persisted replay recovery data must use a versioned query-owned contract (`contract_version`, `answer_basis`, `learning_proposal`, `candidate_proposal`, `writeback_plan`)
- `session.replay_intent` is the authoritative final replay contract and must carry the final `writeback_plan`
- `session_saved` audit details are an immutable seed copy of the same contract family and may omit final write-back outcomes when the request later progresses; they remain valid for recovering answer basis, idempotency ownership, and the original learning/candidate proposals
- replay audit recovery may start from `Idempotency-Key`, but durable recovery ownership must stay anchored to replay-owned state such as the deterministic `session_id`, `mutation_requests`, and frozen targets inside `session.replay_intent`; `request_id` remains attempt-local tracing metadata even when later repair attempts emit additional audits
- retries may finish pending learning-note, candidate, or session-link writes only when the target IDs and proposal fields are already frozen by `session.replay_intent` or the `session_saved` seed copy; replay recovery must never invent new target IDs or mutate the proposal under the same replay owner
- successful idempotent query fixtures must declare `mutation_request_delta`, `mutation_request_status`, and `stored_response_payload` so first-run writes and zero-delta replays still prove the cached replay payload remains in `applied` state
- ordinary requests without `Idempotency-Key` still create normal per-turn session records

This keeps retries safe without turning a client-supplied `X-Request-Id` into the semantic source of truth for mutation replay or audit recovery.

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

- session only, so the validator can replay the same scoped review query safely
- no learning-note writes
- no candidate writes
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
