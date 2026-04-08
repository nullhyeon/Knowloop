# Implementation Plan: Knowloop Backend MVP

## Overview

This plan turns the architecture docs into a backend-first implementation sequence that can be executed by Codex and reviewed by Gemini with low ambiguity.

## Architecture Decisions

- Use a single Python FastAPI backend first to keep orchestration simple.
- Keep knowledge artifacts as files under `data/`, while using SQLite / FTS5 for queryable indexes.
- Keep the skill harness in-repo under `.agents/` so both Codex and Gemini share the same workflows.
- Treat `AGENTS.md`, `SPEC.md`, and `tasks/` as the working source of truth for agents.

## Phase P: Product Contract Lock

- [x] Task P.1: Lock the exact MVP scope and primary demo scenario
- [x] Task P.2: Define entity, identifier, and file naming contracts
- [x] Task P.3: Define role permissions and data access boundaries
- [x] Task P.4: Define candidate creation, promotion, merge, and drop policy
- [x] Task P.5: Define evaluation criteria and demo acceptance checks
- [x] Task P.6: Define query and write-back policy
- [x] Task P.7: Define backend API contracts
- [x] Task P.8: Define repository-safe fixture catalog

### Checkpoint: Planning Locked

- [x] The MVP has one primary story and one secondary story
- [x] Data contracts are concrete enough for storage implementation
- [x] Promotion rules are explicit enough to encode without guessing
- [x] Evaluation criteria can prove the product works in a demo
- [x] Query / write-back behavior is explicit enough to encode without guessing
- [x] API contracts are concrete enough for route and model design
- [x] Fixture coverage is explicit enough to drive bootstrap and tests

Planning lock documents:

- `docs/product/mvp-scope.md`
- `docs/architecture/data-contracts.md`
- `docs/architecture/query-writeback-policy.md`
- `docs/architecture/api-contracts.md`
- `docs/architecture/promotion-policy.md`
- `docs/product/role-permissions.md`
- `docs/product/evaluation-plan.md`
- `docs/product/fixture-catalog.md`
- `docs/product/demo-script.md`
 

## Phase 0: Harness and Runtime Foundation

- [x] Task 0.1: Install `agent-skills` locally under `.agents/`
- [x] Task 0.2: Add shared agent instruction files for Codex and Gemini
- [x] Task 0.3: Create backend runtime scaffold under `apps/api`
- [x] Task 0.4: Add bootstrap, dev, test, and lint scripts
- [x] Task 0.5: Add initial schemas and data-layer directories

### Checkpoint: Foundation Ready

- [x] Backend commands are documented
- [x] Skills exist in the repo
- [x] Project instructions exist for Codex and Gemini

## Phase 1: Storage Bootstrap

- [x] Task 1.1: Define file naming and metadata rules for all knowledge layers
- [ ] Task 1.2: Create SQLite bootstrap for `sessions.db` and `audit.db`
- [ ] Task 1.3: Define candidate lifecycle schema and write helpers
- [ ] Task 1.4: Add repository-safe fixture data for local development

### Checkpoint: Storage Bootstrap

- [ ] Schema contracts reviewed
- [ ] Database bootstrap runs locally
- [ ] Fixture-based tests cover the bootstrap path

## Phase 2: Ingest and Query

- [ ] Task 2.1: Implement raw source registration and manifest updates
- [ ] Task 2.2: Implement session write and session search
- [ ] Task 2.3: Implement candidate creation from query/write-back flow
- [ ] Task 2.4: Implement formal wiki lookup and learning-layer write targets

### Checkpoint: Core Pipeline

- [ ] End-to-end local flow exists for a sample student question
- [ ] Candidate items are created with source links
- [ ] Query path reads the right context layers

## Phase 3: Validation and Maintenance

- [ ] Task 3.1: Add promotion rules and validator interfaces
- [ ] Task 3.2: Add stale detection and orphan checks
- [ ] Task 3.3: Add maintenance report output
- [ ] Task 3.4: Document runbook and handoff expectations

### Checkpoint: Backend MVP Ready

- [ ] API boots cleanly
- [ ] tests pass
- [ ] lint passes
- [ ] maintenance report produces actionable output

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Overbuilding before core flows exist | High | Keep tasks backend-first and small |
| Knowledge-layer contracts drift from docs | High | Update `SPEC.md`, `tasks/`, and ADRs with every structural change |
| Agents skip verification | Medium | Keep verification commands explicit in scripts and prompts |
| Data layout becomes unmanageable | Medium | Define naming rules before implementing storage logic |

## Open Questions

- Should candidate promotion be stored as file frontmatter, SQLite state, or both?
- Should the first ingest format be markdown, JSON, or mixed?
- Which read path should be prioritized first: student query or instructor insight?
