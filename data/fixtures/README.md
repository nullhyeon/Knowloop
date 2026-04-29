# Fixture Data

This directory stores repository-safe fixture files for API tests and storage tests.

Follow the catalog in `docs/product/fixture-catalog.md`.

Canonical MVP fixture pack:

- `learning/`: student learning-note fixtures used by learning-console tests
- `sources/`: lecture notes, announcements, and operations-safe source documents
- `queries/`: request fixtures for `POST /api/v1/query/respond`
  and expected retrieval/write-back contracts
  including setup-driven follow-up scenarios, setup validation, and error envelopes
- `sessions/`: session history seeds used to simulate repeated questions
- `candidates/`: review inbox seeds that match `schemas/candidate_item.json`
- `reviews/`: approve, merge, drop, and patch-preview request fixtures
- `wiki/`: seed pages and expected after-review snapshots

Rules:

- use synthetic or anonymized content only
- keep fixtures small and scenario-focused
- do not place real student, instructor, or institutional data here
- seed test runtime data from these fixtures instead of editing runtime `data/` layers directly
