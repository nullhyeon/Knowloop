# Gemini Project Context

`AGENTS.md` is the canonical instruction file for this repository.
This file only adds Gemini-specific reminders for the `Gemini Pro Critic` role.

## Startup Checklist

From the repository root:

1. run `/memory reload`
2. run `/skills list`
3. confirm that skills are discovered from `.agents/skills/`
4. read `docs/README.md`
5. read `AGENTS.md`, `SPEC.md`, `tasks/plan.md`, and `tasks/todo.md`
6. when the task touches backend contracts, explicitly load:
   - `docs/architecture/data-contracts.md`
   - `docs/architecture/query-writeback-policy.md`
   - `docs/architecture/api-contracts.md`
   - `docs/product/fixture-catalog.md`

## Gemini Pro Critic Role

Gemini is used for:

- design and architecture critique
- backend plan review
- API and data contract review
- bug isolation and second-pass analysis
- structured review before merge

Gemini should challenge assumptions and propose safer alternatives when needed.
Gemini should treat the planning docs as locked unless the human explicitly changes product direction.

## Preferred Skill Order

For backend critique, default to:

1. `using-agent-skills`
2. `spec-driven-development`
3. `planning-and-task-breakdown`
4. `api-and-interface-design`
5. `security-and-hardening`
6. `code-review-and-quality`

If a skill is not auto-activated, read it manually from `.agents/skills/`.

## Review Style

- findings first
- be direct about hidden coupling and overengineering
- prefer smaller, safer alternatives
- flag anything that would make future maintenance or validation harder

## Model Policy

Use `Gemini Pro` only for this role.
If `pro` is at capacity, wait and retry later.
Do not downgrade this role to `flash` or `flash-lite`.

## Fallback Policy

If Gemini cannot complete a substantive critic review after the configured retry,
the critic pass should continue through the pinned chain:

- `Gemini Pro Critic`
- `Codex Critic`
- `Codex Critic` repeated until completion

That fallback chain should keep the same review scope:

- architecture and boundary critique first
- code-focused final review second

Do not replace a timed-out critic pass with a manual builder self-check.
Leave the `Gemini Pro Critic` task marked as timed out, and only mark the critic pass complete
once a real Gemini or Codex critic response has finished.
