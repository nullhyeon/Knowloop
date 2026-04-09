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
| Wiki page | `page-<domain>-<slug>` | `page-faq-homework-submission` |
| Learning note | `learn-<student-id>-<course-id-without-prefix>-<class-id-without-prefix>` | `learn-stu-kim-minji-calculus-1-calculus-1-2026-spring-a` |

### 4.1 Session ID Notes

`POST /api/v1/query/respond` creates session IDs in two modes:

- normal request: timestamp-backed turn ID plus a short random suffix
- idempotent replay: stable ID derived from `Idempotency-Key`

This is intentional:

- repeated genuine questions should still be able to create new session records
- safe client retries should collapse onto the same session when `Idempotency-Key` is supplied

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

Optional but useful fields:

- `tags`
- `related_page_id`
- `approved_at`
- `approved_by`

Canonical store:

- JSON files under `data/candidate/<kind>/<status>/<class-id>/`

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

- Markdown page under `data/wiki/<domain>/<slug>.md`

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
- `request_id`
- `idempotency_key`

Canonical store:

- SQLite table: `audit_events`

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
