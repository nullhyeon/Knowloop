# Current Todo

## Completed

- [x] Install `uv`
- [x] Install Gemini CLI
- [x] Copy `agent-skills` into `.agents/`
- [x] Create `AGENTS.md` and `GEMINI.md`
- [x] Add FastAPI backend scaffold
- [x] Add bootstrap, test, and lint scripts
- [x] Add initial structured output schemas
- [x] Verify Codex CLI login status
- [x] Configure Gemini CLI auth type
- [x] Complete Gemini CLI Google sign-in on this machine

## Next Up

- [x] Planning lock docs completed and wired into the harness
- [x] Codex Builder: implement storage bootstrap for `sessions.db` and `audit.db`
- [x] Codex Reviewer: review the storage bootstrap slice for contract drift and missing tests
- [x] Codex Builder: create the first canonical fixture pack from `docs/product/fixture-catalog.md`
- [x] Codex Builder: define candidate lifecycle write helpers
- [x] Codex Critic fallback: review the candidate lifecycle slice when Gemini Pro is blocked
- [x] Codex Reviewer: review the candidate lifecycle slice for contract drift and missing tests
- [x] Codex Builder: implement dedicated review workflow endpoints
- [x] Gemini Pro Critic: review the review workflow slice for route boundaries, replay safety, and scaling gaps
- [x] Codex Critic fallback: follow up on the review workflow slice and harden the flagged gaps
- [x] Codex Reviewer: review the review workflow slice for correctness, replay coverage, and contract drift

## After First Storage Slice

- [x] Gemini Pro Critic: review storage boundaries and identify over-coupled responsibilities
- [x] Codex Builder: implement raw source registration and manifest updates
- [x] Codex Critic fallback: review the raw source slice for boundary, validation, and contract drift
- [x] Codex Reviewer: review the raw source slice for correctness and missing tests
- [x] Codex Builder: implement `POST /api/v1/query/respond` against fixture-driven tests
- [x] Codex Critic fallback: review the `query/respond` slice for write-back integrity, role boundaries, and hidden coupling
- [x] Codex Reviewer: review the `query/respond` slice for correctness, contract drift, and missing tests

## Next Slice

- [x] Codex Builder: implement dedicated wiki listing and detail endpoints
- [x] Gemini Pro Critic: review the wiki read slice for role exposure, contract clarity, and coupling
- [x] Codex Critic fallback: not needed because Gemini Pro completed the wiki read critic pass
- [x] Codex Reviewer: review the wiki read slice for correctness, contract drift, and missing tests
- [x] Codex Builder: implement instructor insight endpoints against fixture-driven tests
- [x] Gemini Pro Critic: attempted to review the instructor insight slice but did not complete in time
- [x] Codex Critic fallback: review the insight slice when Gemini Pro could not complete the critic pass
- [x] Codex Reviewer: review the insight slice for correctness, contract drift, and missing tests

## Up Next

- [x] Codex Builder: implement session search endpoints and contract tests
- [x] Gemini Pro Critic: attempted to review the session search slice but did not complete in time
- [x] Codex Critic fallback: review the session-search slice when Gemini Pro could not complete the critic pass
- [x] Codex Reviewer: review the session search slice for correctness, contract drift, and missing tests

## Coming Next

- [x] Codex Builder: implement maintenance and stale-detection outputs
- [x] Gemini Pro Critic: attempted to review the maintenance slice but did not complete in time
- [x] Codex Critic fallback: review the maintenance slice when Gemini Pro could not complete the critic pass
- [x] Codex Reviewer: review the maintenance slice for correctness, contract drift, and missing tests

## Next After Maintenance

- [x] Codex Builder: document backend runbook and handoff expectations
- [x] Gemini Pro Critic: review the runbook slice for operational clarity and handoff gaps
- [x] Codex Critic fallback: not needed because Gemini Pro completed the runbook critic pass
- [x] Codex Reviewer: review the runbook slice for contract drift and missing operator guidance

## Next Planning Target

- [x] Codex Builder: strengthen end-to-end query fixture coverage around answer basis and write-back outputs
- [x] Gemini Pro Critic: review the next query-hardening slice for hidden coupling and test blind spots
- [x] Codex Critic fallback: not needed because Gemini Pro completed the query-hardening critic pass
- [x] Codex Reviewer: review the next query-hardening slice for correctness, contract drift, and missing tests

## Next Query Hardening Target

- [x] Codex Builder: add declarative learning-context and error query fixtures
- [x] Gemini Pro Critic: review the next query-hardening slice and flag setup verification, side-effect snapshots, and runtime-ID leakage
- [x] Codex Critic fallback: not needed because Gemini Pro completed the critic pass for this slice
- [x] Codex Reviewer: attempted CLI review, then closed the slice with manual reviewer checks plus full test/lint verification after the follow-up fixes

## Next Promotion Hardening Target

- [x] Codex Builder: tighten candidate-to-wiki promotion coverage and replay expectations
- [x] Gemini Pro Critic: rerun requested for the promotion-hardening slice but Gemini Pro remained capacity-blocked
- [x] Codex Critic fallback: reran the promotion-hardening critic pass and flagged replay, drop-reason, and audit-chain drift
- [x] Codex Builder: fixed promotion replay contract drift, structured drop audit notes, wiki-sync recovery assertions, and resumable pending-sync recovery
- [x] Codex Critic fallback: reran the promotion-hardening critic pass after the follow-up fixes and closed with no material findings
- [x] Codex Reviewer: reran the promotion-hardening reviewer pass after the follow-up fixes and closed with no material findings

## Ready-To-Assign Prompt Targets

- Builder prompt: `.agents/prompts/codex-builder.md`
- Critic fallback prompt: `.agents/prompts/codex-critic.md`
- Reviewer prompt: `.agents/prompts/codex-reviewer.md`
- Critic prompt: `.agents/prompts/gemini-critic.md`
- Backend kickoff prompt: `.agents/prompts/kickoff-backend-foundation.md`
- Storage kickoff prompt: `.agents/prompts/kickoff-storage-bootstrap.md`

## Pre-Frontend Backend Hardening

- [x] Codex Builder: replace heuristic session search scoring with SQLite FTS5-backed search
- [x] Codex Critic: review the FTS-backed session-search slice for index sync, readiness drift, and fallback count risks
- [x] Codex Builder: fix readiness trigger checks and uncapped fallback totals for instructor stopword searches
- [x] Codex Reviewer: review the FTS-backed session-search slice for correctness and missing regressions
- [x] Codex Builder: add a frontend-ready context profile adapter and context bootstrap routes
- [x] Codex Critic: review the context profile slice for profile/header conflicts, route exposure, and contract drift
- [x] Codex Reviewer: review the context profile slice for correctness and missing regressions
- [x] Codex Builder: expose LLM runtime observability through query response metadata and system runtime status
- [x] Codex Critic: review the LLM runtime observability slice for replay ambiguity and provider-authority drift
- [x] Codex Reviewer: review the LLM runtime observability slice for correctness and missing regressions
- [x] Codex Builder: add a one-command backend smoke suite for pre-frontend closure
- [x] Codex Builder: split offline backend smoke from opt-in live LLM smoke and include source registration coverage
- [x] Codex Critic: review the smoke suite slice for representative coverage gaps and brittle coupling
- [x] Codex Reviewer: review the smoke suite slice for correctness and missing regressions

## Backend Logic Hardening Backlog

- [x] P0-prod Codex Builder: replace forgeable request-context headers with an auth-bound or trusted signed-header context adapter, and gate `/api/v1/context/profiles` behind explicit demo mode or authenticated access
- [x] P1 Codex Builder: add practical request bounds for query, source registration, candidate/review decisions, attachment lists, and idempotency keys; include route-level body-size protection and regression tests
- [x] P1 Codex Builder: make query idempotency replay recover from a mutation owner created before session persistence, including stale-owner reclaim and crash-window tests
- [ ] P1 Codex Builder: prevent incomplete write-back mutation payloads from being returned as successful replay responses; repair, complete, or return `storage_busy` until applied
- [ ] P1 Codex Builder: require candidate promotion to resolve and verify every `source_ref` against manifest scope, backing file existence, and checksum before wiki mutation
- [ ] P1 Codex Builder: extract shared stale-lock handling for candidate and wiki locks, align lock contention errors with `storage_busy`, and add crash/stale-lock tests
- [ ] P2 Codex Builder: fix `/api/v1/sessions/recent` pagination so `total`, `offset`, and `limit` are computed from the full visible session set instead of the initial 200/500-row window
- [ ] P2 Codex Builder: persist raw source refs on sessions only when raw fallback is part of the actual answer evidence, or split durable evidence refs from candidate trace refs
- [ ] P2 Codex Builder: harden source ID generation so repeated same-title registrations in the same second cannot collide
- [ ] P2 Codex Builder: move high-volume source, candidate, review, wiki, and maintenance list metadata toward indexed or streaming pagination instead of full-store scans before slicing
- [ ] P2 Codex Builder: make instructor insight aggregation count beyond the current 500-session window or document the window explicitly in the API contract
- [ ] P2 Codex Builder: centralize SQLite connection setup with consistent `busy_timeout`, `foreign_keys`, and retry/WAL policy decisions
- [ ] P3 Codex Builder: resolve `GET /api/v1/sources` filter contract drift by either implementing `course_id`, `class_id`, and `domain` query filters or updating docs to define context-derived scope only
- [ ] P3 Codex Builder: refresh stale backend docs in `apps/api/README.md` and `SPEC.md` so completed query, validation, maintenance, and promotion behavior is no longer described as future work
