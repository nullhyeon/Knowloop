# Knowloop Fixture Catalog

## 1. Purpose

This document defines the repository-safe fixture pack used for:

- API contract tests
- storage bootstrap tests
- workflow integration tests
- demo seeding

Fixtures are not throwaway examples. They are part of the product contract.

## 2. Fixture Principles

1. Fixtures must be repository-safe.
   Only synthetic or anonymized content is allowed.
2. Fixtures should be scenario-focused.
   Keep them small, readable, and easy to trace.
3. Fixtures must map cleanly to MVP workflows.
   They should prove that Knowloop is a memory workflow, not just a chat UI.
4. Fixtures should be deterministic.
   Re-running the same test against the same fixture pack should give stable results.
5. Fixtures should cover boundaries as well as happy paths.
   Role separation, domain separation, and write-back behavior all matter.

## 3. Canonical MVP Pack

Primary course scope:

- `course_id`: `course-calculus-1`
- `class_id`: `class-calculus-1-2026-spring-a`
- primary domain: `academic`

Canonical actors:

- `stu-kim-minji`
- `stu-park-jiyoon`
- `stu-lee-doyun`
- `ins-calculus-team`
- `ops-academic-office`
- `val-course-admin`

Canonical scenario families:

1. chain-rule vs product-rule confusion
2. homework deadline lookup already covered by formal wiki
3. unresolved calculus question that still needs reviewable follow-up
4. operations-domain refund policy handling

## 4. Directory Layout

```text
data/fixtures/
  sources/
  queries/
  sessions/
  candidates/
  reviews/
  wiki/
```

Meaning:

- `sources/`: raw source registration seeds
- `queries/`: request and expected response-shape fixtures for `POST /api/v1/query/respond`
- `sessions/`: prior interaction history used to test retrieval and aggregation
- `candidates/`: review inbox seeds aligned with `schemas/candidate_item.json`
- `reviews/`: future approve, merge, drop, and patch-preview request fixtures
- `wiki/`: seed pages plus expected after-review snapshots

## 5. Source Fixtures

Current fixture files:

- `sources/lecture-note-week-03-chain-rule.md`
- `sources/announcement-homework-deadline.md`
- `sources/instructor-note-chain-rule-support.md`
- `sources/operations-refund-policy.md`

Coverage intent:

- lecture concept grounding
- homework FAQ grounding
- instructional support context
- operations-domain separation

## 6. Query Fixtures

Current fixture files:

- `queries/student-chain-rule-confusion.json`
- `queries/student-homework-deadline-01.json`
- `queries/student-homework-deadline-02.json`
- `queries/student-unresolved-question.json`
- `queries/operator-refund-policy.json`
- `queries/instructor-homework-faq.json`

Expected behavior per fixture:

- `student-chain-rule-confusion.json`
  - answer uses formal wiki and recent session context
  - retrieval refs show `wiki_page` and `session`
  - write-back creates `session`, `learning_note`, and `candidate`
  - candidate kind is `misconception`
- `student-homework-deadline-01.json`
  - answer is satisfied by formal wiki
  - retrieval refs stay on `wiki_page`
  - write-back remains `session` only
- `student-homework-deadline-02.json`
  - repeated homework question still remains `session` only in the MVP because wiki coverage is already sufficient
  - includes `session_context`, but should not create a FAQ candidate automatically for the student path
- `student-unresolved-question.json`
  - answer uses raw fallback without exposing raw source entities to the student response
  - unresolved query may generate a reviewable `unresolved_question` candidate when fallback evidence exists
- `operator-refund-policy.json`
  - validates operations-domain scoping
  - includes `raw_source` retrieval refs for non-student fallback visibility
- `instructor-homework-faq.json`
  - validates the instructor FAQ candidate path
  - remains grounded in formal wiki while writing a high-confidence `faq` candidate
  - aggregates repeated class session links into candidate write-back without exposing raw student transcript bodies in the answer surface

## 7. Session Fixtures

Current fixture files:

- `sessions/student-minji-history.json`
- `sessions/student-jiyoon-history.json`
- `sessions/student-doyun-history.json`
- `sessions/operator-academic-office-history.json`

Coverage intent:

- recent follow-up retrieval
- same-user context continuity
- repeated question patterns
- operations history separation

## 8. Candidate Fixtures

Current fixture files:

- `candidates/open-misconception-chain-rule.json`
- `candidates/open-misconception-chain-rule-duplicate.json`
- `candidates/open-faq-homework-deadline.json`
- `candidates/open-unresolved-integral.json`
- `candidates/open-operations-refund.json`

Coverage intent:

- open review inbox listing
- duplicate merge targets
- FAQ promotion flow
- unresolved knowledge gaps
- operations review flow

## 9. Review Fixtures

Current fixture files:

- `reviews/approve-homework-faq.json`
- `reviews/merge-chain-rule-duplicate.json`
- `reviews/drop-low-value-candidate.json`
- `reviews/patch-preview-homework-faq.json`

These fixtures are kept now so the next review-endpoint slice can be built against them immediately.

## 10. Wiki Fixtures

Current fixture files:

- `wiki/concepts-chain-rule.seed.md`
- `wiki/faq-homework-submission.seed.md`
- `wiki/faq-homework-submission.after.md`
- `wiki/misconception-chain-rule.after.md`
- `wiki/operations-refund-policy.seed.md`

Coverage intent:

- formal concept grounding
- FAQ seed and promoted result snapshot
- misconception page result snapshot
- operations wiki separation

## 11. Coverage Map

| Workflow | Required fixture sets |
|---|---|
| source registration | source |
| student query -> session save | source + query + session history |
| student query -> learning write-back | source + query + session history |
| student query -> candidate write-back | source + query + session history + candidate expectation |
| review inbox and transitions | candidate + review + wiki |
| operations separation | source + query + session history + wiki |

## 12. Current MVP Expectations

The fixture pack intentionally proves these product choices:

- formal wiki is the primary answer layer
- student query retries can be made replay-safe with `Idempotency-Key`
- learning context is personal and only appears when it existed before the current turn
- student homework questions that are already covered by wiki remain session-only
- instructor homework review questions can generate FAQ candidates without changing the student path
- query fixtures lock retrieval entity types and write-back action/status pairs, not only answer basis
- write-back failures should be auditable without turning every query failure into a hard API failure

## 13. Maintenance Rules

When a new backend slice changes fixture semantics, update all of the following together:

- the fixture file itself
- this catalog
- any affected tests
- any related contract documents

A fixture change is a product-contract change, not just a test-data change.
