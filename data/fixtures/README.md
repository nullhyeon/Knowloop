# Fixture Data

This directory stores repository-safe fixture files for demo seeds, API tests, and storage tests.

Follow the catalog in `docs/product/fixture-catalog.md`.

Canonical MVP fixture pack:

- `sources/`: lecture notes, announcements, and operations-safe source documents
- `queries/`: request fixtures for `POST /api/v1/query/respond`
- `sessions/`: session history seeds used to simulate repeated questions
- `candidates/`: review inbox seeds that match `schemas/candidate_item.json`
- `reviews/`: approve, merge, drop, and patch-preview request fixtures
- `wiki/`: seed pages and expected after-review snapshots

Rules:

- use synthetic or anonymized content only
- keep fixtures small and scenario-focused
- do not place real student, instructor, or institutional data here
- seed runtime data from these fixtures instead of editing runtime `data/` layers directly
