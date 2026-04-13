# Documentation Guide

This directory is organized so product, architecture, research, development, and frontend docs stay easy to navigate in GitHub and easy to load for AI agents.

## Recommended Reading Order

1. `product/product-overview.md`
2. `architecture/system-architecture.md`
3. `architecture/system-diagrams.md`
4. `product/mvp-scope.md`
5. `architecture/data-contracts.md`
6. `architecture/query-writeback-policy.md`
7. `architecture/api-contracts.md`
8. `architecture/promotion-policy.md`
9. `product/role-permissions.md`
10. `product/evaluation-plan.md`
11. `product/fixture-catalog.md`
12. `product/demo-script.md`
13. `product/pre-implementation-planning-checklist.md`
14. `product/mvp-patterns.md`
15. `development/agent-harness.md`
16. `development/backend-runbook.md`
17. `frontend/README.md`
18. `research/reference-reading-guide.md` (optional deep-dive)

## Directory Map

- `product/`: product framing, scope, and MVP decisions
- `architecture/`: system layers, flows, and diagrams
- `research/`: external reference reading guides and investigation notes
- `development/`: agent workflow and repository operating conventions
- `frontend/`: page-level frontend structure docs used with `DESIGN.md` and `SITE.md`
- `adr/`: architectural decision records tied to implementation changes

## What Each Core Doc Covers

- `product/product-overview.md`: the problem, target users, core value, and MVP scope
- `product/mvp-scope.md`: the locked MVP scope, non-goals, and primary demo scenario
- `product/pre-implementation-planning-checklist.md`: the decisions that should be locked before implementation starts
- `product/role-permissions.md`: the MVP read/write boundaries for each role
- `product/demo-script.md`: the recommended demo sequence, talk track, and must-show moments
- `product/evaluation-plan.md`: the success criteria, acceptance criteria, and fixture-based evaluation rules
- `product/fixture-catalog.md`: the repository-safe fixture inventory for tests, demos, and storage seeding
- `architecture/system-architecture.md`: the knowledge-layer model and operational design
- `architecture/data-contracts.md`: IDs, entities, metadata, and file/path conventions
- `architecture/query-writeback-policy.md`: the retrieval priority, answer basis, and write-back rules after each query
- `architecture/api-contracts.md`: the HTTP surface, request/response envelopes, role access, and workflow endpoints
- `architecture/promotion-policy.md`: the candidate lifecycle, approval, merge, and drop rules
- `architecture/system-diagrams.md`: mermaid diagrams for use cases, data flow, and sequences
- `product/mvp-patterns.md`: which external patterns were adopted or intentionally excluded
- `development/agent-harness.md`: how Codex and Gemini work inside this repository
- `development/backend-runbook.md`: how to operate, verify, troubleshoot, and hand off the backend
- `development/planning-audit.md`: the current cross-document audit status before implementation
- `frontend/README.md`: how frontend structure docs are organized and which page order to implement
- `DESIGN.md`, `SITE.md`, `component-rules.md`, and `frontend-agent.md`: the frontend source-of-truth files that must be read together before any UI slice
- `research/reference-reading-guide.md`: the research trail behind the architecture decisions

## Public Repo Notes

- Public-facing docs avoid draft-only wording when the content is meant to represent the current direction.
- Internal research remains available, but it lives under `research/` so it does not read like product documentation.
- Secrets and local runtime settings belong in `apps/api/.env`, with defaults documented in `apps/api/.env.example`.
- The backend can be smoke-verified from the repo root with `.\scripts\smoke-api.ps1`.
- Live OpenAI runtime wiring can be checked separately with `.\scripts\live-llm-smoke.ps1`.
- Frontend agents should also read the repo-root files `DESIGN.md`, `SITE.md`, `component-rules.md`, and `frontend-agent.md`.
- Frontend pages should never be implemented without the matching file in `docs/frontend/page-structures/`.
