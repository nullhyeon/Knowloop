# Knowloop Agent Operating Manual

`AGENTS.md` is the canonical instruction file for this repository.
If `AGENTS.md`, `GEMINI.md`, prompts, or chat instructions disagree, follow this file.

## Mission

Build Knowloop as a backend-first `Edu Memory OS` for education workflows:

- preserve `raw sources`
- index `session memory`
- stage uncertain knowledge in `candidate`
- promote validated knowledge into `formal wiki`
- generate `learning layer` artifacts for each student
- run maintenance, audit, and freshness checks continuously

The current priority is backend foundation, not polished frontend work.

## Canonical Context To Read First

When starting a new session, read these files in this order:

1. `docs/README.md`
2. `docs/product/product-overview.md`
3. `docs/product/mvp-scope.md`
4. `docs/architecture/system-architecture.md`
5. `docs/architecture/data-contracts.md`
6. `docs/architecture/query-writeback-policy.md`
7. `docs/architecture/api-contracts.md`
8. `docs/architecture/promotion-policy.md`
9. `docs/product/role-permissions.md`
10. `docs/product/evaluation-plan.md`
11. `docs/product/fixture-catalog.md`
12. `docs/product/demo-script.md`
13. `docs/architecture/system-diagrams.md`
14. `SPEC.md`
15. `tasks/plan.md`
16. `tasks/todo.md`

## Tool and Role Split

We use a 3-role harness built around Codex and Gemini Pro.

### Role 1: Codex Builder

This is the primary implementation agent.

Responsibilities:

- edit repository files
- implement backend slices
- write and update tests
- update `SPEC.md`, `tasks/`, and ADRs when decisions change
- keep the repo runnable after each completed slice

Operating rule:

- focus on one planned task at a time
- prefer minimal, verifiable changes
- do not self-approve risky architectural changes without surfacing tradeoffs

### Role 2: Gemini Pro Critic

This is the architecture challenger and risk detector.

Responsibilities:

- critique plans before large implementation
- review data boundaries and API contracts
- challenge assumptions and overengineering
- suggest simpler alternatives
- identify maintainability, privacy, and operational risks

Operating rule:

- default to critique before code, not code before critique
- review a specific task, diff, or plan instead of the whole repo at once
- findings first, recommendations second

### Role 3: Codex Reviewer

This is the code-focused reviewer and test gap finder.

Responsibilities:

- review uncommitted or branch diffs
- check spec alignment
- detect missing tests, contract drift, or brittle code
- propose focused fixes or follow-up tasks

Operating rule:

- default to review mode before edit mode
- prefer `.\scripts\run-codex-review.ps1` for the repository's pinned reviewer path
- if patching issues directly, update docs and verification results too

## Skill System

This repository uses the `agent-skills` harness from Addy Osmani as local, tool-neutral project skills.

- Skills live in `.agents/skills/<skill-name>/SKILL.md`
- Review personas live in `.agents/agents/`
- Reference checklists live in `.agents/references/`
- Prompt starters live in `.agents/prompts/`

Every non-trivial task must start with skill discovery:

1. Read `.agents/skills/using-agent-skills/SKILL.md`
2. Select the matching skill
3. Follow the skill process, including verification
4. Update repo artifacts as required by that skill

## Mandatory Lifecycle

For any feature-sized task, follow this order:

1. `spec-driven-development`
2. `planning-and-task-breakdown`
3. `context-engineering`
4. `incremental-implementation`
5. `test-driven-development`
6. `code-review-and-quality`
7. `documentation-and-adrs`

Add these when relevant:

- `api-and-interface-design` for API contracts or module boundaries
- `security-and-hardening` for anything touching user input, files, or storage
- `debugging-and-error-recovery` when behavior is broken or uncertain
- `frontend-ui-engineering` only after frontend work begins

## Recommended Working Loop

1. `Codex Builder` reads the task and implements the next slice.
2. `Gemini Pro Critic` challenges the plan or the change set.
3. `Codex Builder` integrates the valid critique.
4. `Codex Reviewer` performs final code review and test-gap review.
5. Update `tasks/todo.md` and any affected docs.

## Backend-First Scope

Current backend phases:

### Phase 0: Harness and Runtime Foundation

- local skill installation
- shared agent instruction files
- FastAPI scaffold
- repo scripts and commands
- data directory layout
- JSON schema contracts for structured agent output

### Phase 1: Core Storage and Index Bootstrap

- raw source manifest
- sessions database bootstrap
- candidate store layout and lifecycle
- wiki and learning write targets

### Phase 2: Ingest and Query Pipeline

- source ingest
- session write and retrieval
- candidate generation
- query orchestration and write-back

### Phase 3: Maintenance and Validation

- lint and health checks
- stale detection
- promotion rules
- human validation workflow

## Working Artifacts

The following files are living documents and must stay in sync with the code:

- `SPEC.md`
- `tasks/plan.md`
- `tasks/todo.md`
- `docs/adr/`
- `schemas/`

If scope or architecture changes, update the document first or together with the code.

## Boundaries

### Always

- state assumptions before major work
- keep tasks small and verifiable
- run tests and lint before declaring work complete
- update specs, plans, and ADRs when decisions change
- keep the backend runnable after each completed slice
- preserve source traceability for all knowledge artifacts

### Ask first

- adding a new external paid service
- introducing a vector database before FTS5 is insufficient
- adding authentication or role-based access beyond the current MVP
- changing the repo layout in a way that invalidates current docs
- introducing background workers, queues, or multi-service deployment

### Never

- bypass the `candidate` layer for unverified knowledge
- commit real student PII, secrets, or private source material
- skip verification because the change `looks right`
- delete docs or data structures that you do not fully understand
- mix unrelated refactors into a task unless explicitly requested

## Verification Bar

Do not call a task done until you have evidence:

- tests pass
- lint passes
- the app boots if runtime code changed
- changed docs reflect the current implementation

If a command cannot be run, say exactly what was not verified.

## Handoff Format

When handing work from one agent to another, include:

1. role requested
2. goal
3. files touched or under review
4. skill(s) used
5. verification performed
6. open risks or open questions

