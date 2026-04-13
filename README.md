# Knowloop

Knowloop is a backend-first workspace for an education-focused memory OS:

- `raw -> candidate -> formal wiki -> learning -> maintenance`
- backend foundation first, frontend after the data and agent workflow are stable
- Codex and Gemini share the same workspace rules and skill library
- the working loop is `Codex Builder -> Gemini Pro Critic -> Codex Critic retry chain if needed -> Codex Reviewer`

## Current Stack

- Python 3.12
- FastAPI
- SQLite / FTS5 (planned MVP storage)
- Markdown knowledge layers under `data/`
- `uv` for environment and task execution
- `pytest` and `ruff`
- `agent-skills` installed locally under `.agents/`

## Documentation

- `docs/README.md`
- `docs/product/product-overview.md`
- `docs/product/mvp-scope.md`
- `docs/product/pre-implementation-planning-checklist.md`
- `docs/architecture/system-architecture.md`
- `docs/architecture/data-contracts.md`
- `docs/architecture/query-writeback-policy.md`
- `docs/architecture/api-contracts.md`
- `docs/architecture/promotion-policy.md`
- `docs/architecture/system-diagrams.md`
- `docs/product/role-permissions.md`
- `docs/product/evaluation-plan.md`
- `docs/product/fixture-catalog.md`
- `docs/product/demo-script.md`
- `docs/product/mvp-patterns.md`
- `docs/development/agent-harness.md`
- `docs/development/backend-runbook.md`

## Model Policy

- `Codex Builder`: `gpt-5.4` + `xhigh`
- `Codex Reviewer`: `gpt-5.4` + `xhigh`
- `Gemini Pro Critic`: `pro` only
- `Codex Critic`: `gpt-5.4` + `xhigh` fallback when Gemini cannot complete the critic pass

If Gemini Pro is at capacity or cannot complete a substantive pass, continue through the pinned critic retry chain. Do not downgrade the critic role to a lower-quality model and do not substitute manual builder self-review for missing critic or reviewer passes.

## Environment

The API reads local settings from `apps/api/.env`.

Safe defaults are documented in `apps/api/.env.example`.

## Quick Start

```powershell
cd C:\Users\wowjd\Desktop\Knowloop
.\scripts\bootstrap.ps1
.\scripts\dev-api.ps1
```

In another terminal:

```powershell
cd C:\Users\wowjd\Desktop\Knowloop
.\scripts\test-api.ps1
.\scripts\lint-api.ps1
.\scripts\smoke-api.ps1
```

Optional live provider smoke when `apps/api/.env` enables the OpenAI runtime:

```powershell
cd C:\Users\wowjd\Desktop\Knowloop
.\scripts\live-llm-smoke.ps1
```

## Agent Sessions

Script naming:

- `start-*.ps1` opens an interactive agent session
- `run-*.ps1` runs a focused one-shot pass for critique or review

Check auth state:

```powershell
.\scripts\check-agent-auth.ps1
```

Start the builder:

```powershell
.\scripts\start-codex-builder.ps1
```

Run a final Codex review on local changes:

```powershell
.\scripts\run-codex-review.ps1
```

Run the Codex Critic fallback on local changes:

```powershell
.\scripts\run-codex-critic.ps1
```

Run Gemini Pro Critic as a one-shot pass:

```powershell
.\scripts\run-gemini-critic.ps1
```

If Gemini cannot complete the critic pass, continue with Codex Critic on the same narrowed review package:

```powershell
.\scripts\run-codex-critic.ps1
```

Inside the Codex desktop thread, the preferred path is to use Codex subagents
for `Critic` and `Reviewer` roles and keep these scripts as reproducible
fallbacks for standalone or human-driven runs.

Reconnect Codex if ever needed:

```powershell
.\scripts\connect-codex.ps1
```

Start Gemini Pro Critic:

```powershell
.\scripts\start-gemini-critic.ps1
```

Reconnect Gemini if ever needed:

```powershell
.\scripts\connect-gemini.ps1
```

## Agent Workflow

1. Read `AGENTS.md`.
2. Use `SPEC.md` as the implementation source of truth.
3. Use `tasks/plan.md` and `tasks/todo.md` as living execution artifacts.
4. Load the relevant skill from `.agents/skills/` before working.
5. Prefer the 3-role loop for non-trivial changes.

More detail lives in `docs/development/agent-harness.md`.
