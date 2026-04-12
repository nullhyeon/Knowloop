# Knowloop Data Contracts

## 1. Purpose

This document locks the storage and identifier contracts that every backend slice must follow.
It is the source of truth for:

- entity boundaries
- identifier formats
- canonical storage locations
- required metadata for traceability
- which layer is authoritative for each record type

The goal is to keep implementation, fixtures, and API behavior aligned even as the system grows.

## 2. Contract Principles

1. Every durable record must be traceable.
   We should always be able to answer which source, session, or review action produced it.
2. Layers stay separate.
   Raw sources, sessions, candidates, formal wiki, learning notes, and audit events do not share one storage shape.
3. IDs must be stable and readable.
   They should be safe for URLs, filenames, logs, and Git diffs.
4. Public knowledge and personal learning state are different assets.
   Formal wiki is shared knowledge. Learning notes are personal support state.
5. Session writes are append-only at the interaction level.
   Query turns create durable session records; follow-up linking may enrich them, but does not replace the turn.

## 3. Shared Conventions

### 3.1 Slugs

- lowercase ASCII only
- words separated by `-`
- no spaces or path separators

Examples:

- `week-03-chain-rule`
- `homework-01-submission`
- `chain-rule-product-rule-confusion`

### 3.2 Time

- API payloads use UTC ISO 8601 timestamps, for example `2026-04-08T10:30:00Z`
- filename and ID suffixes may use compact UTC timestamps, for example `20260408T103000Z`

### 3.3 Roles

Canonical role values:

- `student`
- `instructor`
- `operator`
- `validator`
- `system`

### 3.4 Common Status Values

Common lifecycle values used across the MVP:

- `registered`
- `open`
- `promoted`
- `merged`
- `dropped`
- `failed`

## 4. Identifier Formats

| Entity | Format | Example |
|---|---|---|
| Student actor | `stu-<slug>` | `stu-kim-minji` |
| Instructor actor | `ins-<slug>` | `ins-calculus-team` |
| Operator actor | `ops-<slug>` | `ops-academic-office` |
| Validator actor | `val-<slug>` | `val-course-admin` |
| Course | `course-<slug>` | `course-calculus-1` |
| Class | `class-<course-slug>-<term>-<section>` | `class-calculus-1-2026-spring-a` |
| Raw source | `src-<source-type>-<scope-token>-<slug>-<timestamp>` | `src-lecture-note-class-calculus-1-2026-spring-a-week-03-20260408T103000Z` |
| Session | `ses-<role>-<user-id>-<class-id>-<token>` | `ses-student-stu-kim-minji-class-calculus-1-2026-spring-a-7df8a1b0c2` |
| Candidate | `cand-<kind>-<class-id>-<slug>-<timestamp>` | `cand-misconception-class-calculus-1-2026-spring-a-chain-rule-20260408T112000Z` |
| Wiki page | `page-<domain>-<slug>` scoped by `course_id + class_scope` | `page-faq-homework-submission` |
| Learning note | `learn-<student-id>-<course-id-without-prefix>-<class-id-without-prefix>` | `learn-stu-kim-minji-calculus-1-calculus-1-2026-spring-a` |

### 4.1 Session ID Notes

`POST /api/v1/query/respond` creates session IDs in two modes:

- normal request: timestamp-backed turn ID plus a short random suffix
- idempotent replay: stable ID derived from the normalized replay scope plus `Idempotency-Key`

This is intentional:

- repeated genuine questions should still be able to create new session records
- safe client retries should collapse onto the same session only inside the same normalized replay scope
- the normalized replay scope for query sessions is `role + actor_id + course_id + class_id + domain`
- session ID derivation is deliberately narrower than the full replay fingerprint: it stays stable for same-scope retries, while the full normalized query body still determines whether the request is replay-compatible or must return `409 duplicate_action`

### 4.2 Raw Source ID Notes

Raw source IDs follow the implementation rules in `services/sources.py`.

- most source types use `src-<source-type>-<class-id>-<slug>-<timestamp>`
- flexible-domain source types such as `announcement` include a short domain token before the class ID, for example `src-announcement-acad-class-calculus-1-2026-spring-a-...`
- title slugs include a digest suffix so long titles, repeated titles, and non-ASCII titles do not collapse into the same durable ID

## 5. Core Entities

### 5.1 RawSource

Purpose: immutable source material registered into the system.

Required fields:

- `source_id`
- `source_type`
- `domain`
- `title`
- `course_id`
- `class_id`
- `actor_role`
- `created_at`
- `origin_path`
- `checksum`
- `status`

Optional fields:

- `uploaded_by`
- `mime_type`
- `filename`
- `tags`

Canonical store:

- metadata: manifest-backed record under `data/meta/manifest.json`
- file payload: `data/raw/...`

### 5.2 SessionRecord

Purpose: one durable question-answer interaction.

`user_id` is the persisted actor identity for the turn. It is populated from the request context's `actor_id`.

Required fields:

- `session_id`
- `role`
- `user_id`
- `course_id`
- `class_id`
- `question`
- `answer`
- `created_at`

Optional but expected fields:

- `tags`
- `source_refs`
- `retrieval_refs`
- `candidate_refs`
- `learning_note_refs`
- `replay_intent`

Canonical store:

- SQLite table: `sessions`
- export file: `data/sessions/<role>/<class-id>/<user-id>/<session_id>.json`

### 5.3 CandidateItem

Purpose: reviewable structured knowledge signal that has not yet been promoted into formal wiki.

Required fields:

- `candidate_id`
- `kind`
- `status`
- `title`
- `summary`
- `course_id`
- `class_id`
- `confidence`
- `source_refs`
- `session_refs`
- `created_at`
- `updated_at`

Optional but useful fields:

- `tags`
- `related_page_id`
- `approved_at`
- `approved_by`
- `promotion_attempt_id`
- `wiki_sync_target_path`
- `approval_plan_fingerprint`
- `wiki_sync_status`
- `wiki_synced_at`

Interpretation notes:

- `updated_at` is the canonical freshness timestamp for maintenance and review tooling
- legacy candidate files that predate `updated_at` must be normalized on read so runtime
  services still see the canonical shape; the on-disk rewrite is best-effort and may be
  retried later if the first normalization write fails
- `promotion_attempt_id` is the server-owned identity for one approval attempt
- `wiki_sync_target_path` and `approval_plan_fingerprint` freeze the exact wiki patch plan that may later be resumed
- `wiki_sync_status = pending` means the candidate is promoted but the wiki sync still needs the dedicated resume path to finish

Canonical store:

- JSON files under `data/candidate/<kind>/<class-id>/<candidate-id>.json`

Notes:

- `<kind>` means the canonical candidate directory token such as `misconceptions`, `faq`, `interventions`, `unresolved-questions`, or `operations-notes`
- candidate status lives in the JSON body, not in the directory name
- the durable path must stay stable across `open -> promoted -> merged -> dropped`

### 5.4 WikiPage

Purpose: verified shared knowledge used as the primary answer basis.

Required fields in frontmatter:

- `page_id`
- `domain`
- `title`
- `course_id`
- `class_scope`
- `updated_at`
- `summary`
- `source_refs`
- `candidate_refs`

Canonical store:

- Markdown page under `data/wiki/<domain>/<class-id>/<slug>.md`

Notes:

- `page_id` is resolved inside the current `course_id + class_scope` boundary
- wiki page slugs only allow lowercase letters, digits, and hyphens; path separators or traversal segments are invalid
- the storage path carries the class scope so two classes can promote the same wiki slug without colliding on disk
- legacy unscoped wiki files under `data/wiki/<domain>/<slug>.md` are no longer canonical; normal wiki reads ignore them and maintenance must surface them as migration-required layout issues
- a file stored under `data/wiki/<domain>/<class-id>/...` is owned by that class path; if its frontmatter points to another scope, maintenance must surface it as invalid metadata rather than silently skipping it
- if a legacy unscoped file is unreadable, scoped maintenance only surfaces it when matching `class_scope` survives and any surviving `course_id` also matches the current course; `course_id` alone is not enough to attribute it to one class boundary

### 5.5 LearningNote

Purpose: student-scoped learning support profile for one course and class.

Required fields:

- `learning_note_id`
- `student_id`
- `course_id`
- `class_id`
- `created_at`

Common content fields:

- `concepts`
- `gaps`
- `next_actions`
- `flashcards`
- `source_refs`
- `session_refs`
- `summary`
- `updated_at`

Canonical store:

- `data/learning/students/<student-id>/<course-id>/<class-id>/notes.md`
- `data/learning/students/<student-id>/<course-id>/<class-id>/gaps.md`
- `data/learning/students/<student-id>/<course-id>/<class-id>/next_actions.md`

### 5.6 AuditEvent

Purpose: immutable record of storage mutations and recovery events.

Required fields:

- `event_id`
- `entity_type`
- `entity_id`
- `action`
- `actor_role`
- `created_at`

Optional fields:

- `actor_id`
- `from_status`
- `to_status`
- `notes`
- `details_json` for action-specific structured metadata; the current MVP contract uses it for drop `reason`, query `session_saved` replay seeds, and other action-scoped recovery details that are explicitly locked by the owning workflow contract
- `request_id`
- `idempotency_key`

Canonical store:

- SQLite table: `audit_events`

Structured `details_json` contracts locked in the MVP:

- `candidate_dropped`
  - `reason`
- `session_saved`
  - immutable `QueryReplayIntent` seed used for bounded replay recovery when the final `sessions.replay_intent` copy has not been refreshed yet
- `candidate_wiki_sync_pending`
  - `candidate_id`
  - `promotion_attempt_id`
  - `approval_plan_fingerprint`
- `wiki_patch_applied`
  - `candidate_id`
  - `promotion_attempt_id`
  - `approval_plan_fingerprint`
- `candidate_wiki_synced`
  - `candidate_id`
  - `promotion_attempt_id`
  - `approval_plan_fingerprint`

Interpretation notes:

- the three wiki-sync audit actions above form a single frozen promotion-attempt chain
- `candidate_id` is always required for that chain, even on the `wiki_page`-owned `wiki_patch_applied` event, so replay recovery can correlate the page mutation back to the candidate that owns the frozen approval plan
- `promotion_attempt_id` and `approval_plan_fingerprint` identify the immutable promotion attempt that replay and resume logic must converge onto
- read-side legacy compatibility checks for wiki-sync audits operate over the full `entity_type + entity_id + action` chain, not only rows whose `idempotency_key` is `NULL`
- legacy pre-details rows may still exist for older promotion attempts; replay recovery may treat them as compatible only when that `entity_type + entity_id + action` chain is otherwise unique, but new writes must persist the structured details above
- candidate-owned wiki-sync actions may upgrade a unique legacy row in place; page-owned `wiki_patch_applied` rows must preserve historical attempts when the frozen promotion identity cannot be proven from the existing row

### 5.7 MutationRequest

Purpose: replay-owner record for idempotent mutations that are still pending, recovering, or already accepted.

Required fields:

- `entity_type`
- `entity_id`
- `action`
- `idempotency_key`
- `actor_role`
- `request_fingerprint`
- `status`
- `created_at`
- `updated_at`

Optional but expected fields:

- `actor_id`
- `response_payload`

Status values:

- `pending`
- `applied`

Interpretation notes:

- for query mutations, `entity_id` is the deterministic `session_id` derived from the normalized replay scope plus `Idempotency-Key`
- the normalized replay scope for query mutations is `role + actor_id + course_id + class_id + domain`; when `domain` is omitted, it is normalized using `Public Query Default Domains v1` before `session_id` derivation
- query mutations do not persist `course_id`, `class_id`, or `domain` as standalone `mutation_requests` columns in the current MVP; those scope components stay encoded inside the deterministic `session_id`, while `actor_role`, `actor_id`, and `request_fingerprint` remain first-class columns
- `request_fingerprint` is the canonical effective-request fingerprint for that replay scope; for query mutations it is derived from the normalized body contract only: trimmed `message`, sorted+deduplicated `attachment_source_ids`, `allow_raw_source_fallback`, and `response_mode`
- `status=pending` means the mutation owns the replay reservation but may still be computing or repairing durable side effects
- pending replay ownership is a bounded liveness lease keyed by `updated_at`; active work refreshes that timestamp and retries may treat the reservation as stale after the lease window expires
- `status=applied` means the mutation owns the accepted replay result and `response_payload` is the canonical replayable API `data` payload
- query routes must create the replay-owner row only after the request has passed scope and verified-context gates; rejected requests do not leave durable `mutation_requests` rows behind
- incomplete or degraded pending rows are treated as recovery state, not as reusable accepted replay state; callers must receive bounded retry semantics until cleanup or recovery can re-establish a valid owner
- a durable session row may already exist while the matching replay-owner row is still `pending`; read surfaces may expose that session row inside the normal role boundary, but idempotent replay is not considered durably accepted until the matching `mutation_requests` row reaches `applied`
- cleanup or recovery after a failed in-flight mutation must not leave a stale `pending` reservation that permanently blocks future retries under the same normalized scope and `Idempotency-Key`

Canonical store:

- SQLite table: `mutation_requests`

### 5.8 QueryReplayIntent

Purpose: authoritative query-owned recovery contract for rebuilding accepted replay results and finishing bounded write-back repair without inventing new targets.

Required fields:

- `contract_version`
- `answer_basis`
- `writeback_plan`

Optional but expected fields:

- `idempotency_key`
- `learning_proposal`
- `candidate_proposal`

Interpretation notes:

- the authoritative final copy lives in `sessions.replay_intent`
- `audit_events.details_json` on the `session_saved` action stores an immutable seed copy of the same contract family for recovery when the final session row has not yet been refreshed
- `mutation_requests.response_payload` stores the accepted API `data` payload for replay, not a second independent write-back proposal schema
- for review `resume-sync`, `mutation_requests.response_payload` may also carry an internal `_resume_contract` object containing the frozen `promotion_attempt_id` and `approval_plan_fingerprint`; this is storage metadata for replay ownership, not part of the public HTTP response contract
- replay recovery may repair unfinished learning-note, candidate, or session-link writes only when the target IDs and write-back plan are already frozen by this contract family; retries must not invent new target IDs or generate a different proposal under the same replay owner

Contract schema:

- `schemas/query_replay_intent.json`

## 6. Source Reference Contract

`source_refs` are intentionally small and portable.
Each source reference contains:

- `source_id`
- `source_type`
- optional `chunk_id`

Rules:

- candidates and learning notes keep source references for traceability
- student-facing retrieval refs do not expose raw source metadata directly
- formal wiki pages list the raw source IDs they were derived from

## 7. Storage Layout

```text
data/
  raw/
  sessions/
  candidate/
  wiki/
  learning/
  meta/
  fixtures/
```

Layer responsibilities:

- `raw/`: durable source files as registered
- `sessions/`: exported session snapshots for inspection and debugging
- `candidate/`: review inbox material in JSON form
- `wiki/`: formal verified Markdown pages
- `learning/`: student-scoped learning support files
- `meta/`: manifest, scoped maintenance reports, and SQLite databases
- `fixtures/`: repository-safe test and demo seeds

## 8. Authority Rules

The authoritative store for each layer is:

- raw sources: manifest record plus file on disk
- sessions: SQLite `sessions` table
- candidates: JSON file in candidate storage
- wiki: Markdown page in `data/wiki`
- learning: Markdown files in the student learning directory
- audit: SQLite `audit_events` and `mutation_requests`

Exported or derived views must follow the authoritative store, not the other way around.

Scoped maintenance report path:

```text
data/meta/maintenance/{course_id}/{class_id}/lint-status.json
```

Rules:

- maintenance reports are course/class scoped, not global
- the maintenance status surface reads the scoped persisted report for the current request context
- report generation must not overwrite another class scope's maintenance output
- maintenance checks must read the authoritative wiki pages under `data/wiki`, not a cached secondary index

## 9. Implementation Notes

- `announcement` can belong to either `academic` or `operations` domain; domain decides its boundary, not source type alone.
- A learning note is scoped to `student + course + class`, not to the entire student profile.
- Query writes may enrich a session with `candidate_refs` or `learning_note_refs` after the initial session row is saved.
- Open candidates are never treated as formal truth.

## 10. Change Control

Any implementation change that alters:

- ID shapes
- canonical storage locations
- required fields
- authority rules

must update this document, the corresponding schemas, and any affected fixture files in the same change set.
