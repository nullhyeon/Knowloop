# Agent Harness

This repository uses `agent-skills` as a local, cross-agent engineering harness.

For the human-readable doc map, start with `docs/README.md`.

## Installed Assets

- Skills: `.agents/skills/`
- Review personas: `.agents/agents/`
- References: `.agents/references/`
- Prompt starters: `.agents/prompts/`

## Canonical Instruction Files

- Primary: `AGENTS.md`
- Gemini supplement: `GEMINI.md`
- Working artifacts: `docs/README.md`, `SPEC.md`, `tasks/plan.md`, `tasks/todo.md`

## The Four Roles

### Codex Builder

Use for implementation.

Read:

- `docs/README.md`
- `AGENTS.md`
- `SPEC.md`
- `tasks/plan.md`
- `tasks/todo.md`

Then use `.agents/prompts/codex-builder.md`.

This role is pinned to `gpt-5.4` with `xhigh` reasoning effort.

### Gemini Pro Critic

Use for critique before or after implementation.

Read:

- `docs/README.md`
- `AGENTS.md`
- `GEMINI.md`
- `SPEC.md`
- `tasks/plan.md`
- `tasks/todo.md`

Then use `.agents/prompts/gemini-critic.md`.

This role is `pro-only`. If `pro` is busy, wait and retry. Do not downgrade the model.

### Codex Critic

Use when `Gemini Pro Critic` cannot complete the critic pass in a reasonable
time or when the Gemini CLI is temporarily unavailable.

Fast path:

```powershell
.\scripts\run-codex-critic.ps1
```

Prompt path:

- read `docs/README.md`
- read `AGENTS.md`
- read `SPEC.md`
- use `.agents/prompts/codex-critic.md`

This role is pinned to `gpt-5.4` with `xhigh` reasoning effort.
It should stay focused on architecture critique rather than patch-level review.

### Codex Reviewer

Use for a final code-focused review and test-gap check.

Fast path:

```powershell
.\scripts\run-codex-review.ps1
```

Prompt path:

- read `AGENTS.md`
- read `docs/README.md`
- read `SPEC.md`
- use `.agents/prompts/codex-reviewer.md`

This role is pinned to `gpt-5.4` with `xhigh` reasoning effort.

## Recommended Working Loop

1. Codex Builder implements the next planned slice.
2. Gemini Pro Critic challenges the design, boundaries, and risks.
3. If Gemini Pro Critic is blocked, Codex Critic performs the critic pass.
4. Codex Builder integrates valid critique.
5. Codex Reviewer performs final diff review.
6. Update `tasks/todo.md` and relevant docs.

## Authentication Status

- Codex CLI is logged in on this machine.
- Gemini CLI is authenticated on this machine.
