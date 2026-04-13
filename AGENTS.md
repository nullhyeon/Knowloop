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

We use a 4-role harness built around Codex and Gemini Pro.

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
- use a generated `review package` as the default input, not the raw worktree
- findings first, recommendations second
- this is the preferred critic when `Gemini Pro` is responsive

### Role 3: Codex Critic

This is the fallback architecture challenger when `Gemini Pro Critic` is blocked,
times out, or cannot complete a substantive review.

Responsibilities:

- perform the same architecture critique expected from Gemini
- challenge assumptions before implementation lands
- review data boundaries and API contracts
- identify hidden coupling, privacy risk, and operational drift
- offer smaller or safer alternative designs

Operating rule:

- use this role when Gemini cannot complete the critic pass in a reasonable time
- keep the review scoped to a specific slice, diff, or contract area
- inherit the same `review package` scope that Gemini received
- findings first, recommendations second
- do not collapse into code-style review; leave patch-level review to `Codex Reviewer`
- do not replace this role with a manual builder self-check when it times out; retry until an actual critic response completes

### Role 4: Codex Reviewer

This is the code-focused reviewer and test gap finder.

Responsibilities:

- review uncommitted or branch diffs
- check spec alignment
- detect missing tests, contract drift, or brittle code
- propose focused fixes or follow-up tasks

Operating rule:

- default to review mode before edit mode
- prefer `.\scripts\run-codex-review.ps1` for the repository's pinned reviewer path
- use a `review package` built from the active slice, not the whole worktree
- if patching issues directly, update docs and verification results too
- do not replace this role with a manual builder self-check when it times out; retry until an actual reviewer response completes

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
2. `Codex Builder` runs tests, lint, and `git diff --check` before any review pass.
3. `Codex Builder` builds a narrow `review package` for the active slice.
4. `Gemini Pro Critic` or `Codex Critic` challenges the plan or the change set using that package.
5. Prefer real Codex subagents for `Critic` and `Reviewer` work when operating inside Codex. Use the local scripts as a fallback for standalone CLI runs or when a human wants to reproduce the same review package flow outside the thread.
6. If `Gemini Pro Critic` is blocked or times out, continue the pinned critic chain as `Gemini Pro -> Codex Critic -> Codex Critic ...` using the same package until a critic pass completes.
7. If a package times out, narrow the package before retrying. Do not keep resending the same large scope.
8. `Codex Builder` integrates the valid critique.
9. `Codex Reviewer` performs final code review and test-gap review against a reviewer package, retrying until a reviewer pass completes.
10. Update `tasks/todo.md` and any affected docs.

## Review Package Policy

All critic and reviewer runs must use a generated `review package`.

Package contents:

- slice name
- goal and review focus
- files under review
- relevant contract docs
- narrow diff only

Package rules:

- default package size is `<= 3 files` and about `<= 300 diff lines`
- if a package times out, retry with a narrower package before retrying the same large scope
- for multi-file packages, prefer one quick attempt and then split
- for single-file packages, retry the same role until it completes
- do not send the entire repo or full worktree unless the human explicitly asks for a broad review

## Timeout Policy

Timeout does not count as role completion.

- Never replace a timed-out critic or reviewer pass with a manual builder self-check.
- In Codex, prefer subagents for critic and reviewer work.
- For standalone script-driven critic passes, use `.\scripts\run-gemini-critic.ps1` first and then `.\scripts\run-codex-critic.ps1` if Gemini cannot complete.
- For standalone script-driven reviewer passes, use `.\scripts\run-codex-review.ps1`.
- If a role times out on a multi-file package, narrow the package before retrying.
- If a role times out on a single-file package, keep retrying that role until a real response completes or the human explicitly interrupts the run.
- Report timeout history honestly in the final task report, but only after a critic or reviewer response has actually completed.
- If we reopen an older slice because a real critic or reviewer pass was missing, treat the rerun, fixes, validation, and follow-up review as one work unit before closing it again.

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

