# Backend Runbook

## 1. Purpose

This runbook explains how to operate, verify, and hand off the current Knowloop backend MVP workspace.
It is written for two audiences:

- the repository owner coordinating delivery
- AI agents or future collaborators continuing backend work

This is not a product spec.
It is the practical operating guide for the current backend.

## 2. Current Backend Scope

The current backend supports these route families:

- health and readiness
- source registration and lookup
- query and write-back
- review workflow
- wiki read routes
- instructor insight routes
- session search routes
- maintenance report routes

The backend is still MVP-scoped.
It is intentionally backend-first and file-plus-SQLite based.

## 3. Safety Rules

Always keep these rules in force:

1. Never skip the `candidate` layer for unverified knowledge.
2. Never commit private educational data, secrets, or real student records.
3. Never treat open candidates as formal truth.
4. Never let public query routes write directly to formal wiki pages.
5. Never overwrite another course/class scope's maintenance output.

## 4. Canonical Commands

Script naming:

- `start-*.ps1` opens an interactive session that a human can continue using
- `run-*.ps1` performs a one-shot focused pass and returns immediately with findings or status

Run all commands from the repository root unless noted.

Bootstrap dependencies:

```powershell
.\scripts\bootstrap.ps1
```

Run the API:

```powershell
.\scripts\dev-api.ps1
```

Run tests:

```powershell
.\scripts\test-api.ps1
```

Run lint:

```powershell
.\scripts\lint-api.ps1
```

Check agent authentication:

```powershell
.\scripts\check-agent-auth.ps1
```

## 5. Preflight Checklist

Before starting a new backend slice:

1. Read `AGENTS.md`.
2. Read `docs/README.md`.
3. Read `SPEC.md`.
4. Read `tasks/plan.md` and `tasks/todo.md`.
5. Read the contract docs relevant to the slice.
6. Confirm the worktree is clean or intentionally dirty.
7. Confirm `apps/api/.env` exists and matches local expectations.
8. Confirm fixture-driven work can be done without introducing private data.

## 6. Runtime Verification

Minimum local verification:

1. `.\scripts\test-api.ps1`
2. `.\scripts\lint-api.ps1`

When the API is running, these routes should be usable:

- `GET /healthz`
- `GET /readyz`
- `GET /api/v1/system/health`
- `GET /api/v1/system/ready`

Readiness depends on storage bootstrap completing successfully.

## 7. Data and Storage Expectations

Current authoritative layers:

- raw sources: manifest record plus durable file under `data/raw`
- sessions: SQLite session store
- candidates: JSON files plus audit trail
- wiki: Markdown under `data/wiki`
- learning: scoped Markdown files under `data/learning`
- audit: SQLite audit and mutation tables
- maintenance reports: `data/meta/maintenance/{course_id}/{class_id}/lint-status.json`

Rules:

- fixture data must remain synthetic or anonymized
- path and ID rules come from `docs/architecture/data-contracts.md`
- route behavior comes from `docs/architecture/api-contracts.md`

## 8. Working Loop

Every non-trivial backend task should follow this order:

1. `Codex Builder` implements the slice.
2. `Gemini Pro Critic` reviews boundaries, risk, and overengineering.
3. If Gemini cannot complete, `Codex Critic` performs the critic pass.
4. `Codex Reviewer` performs a final correctness and test-gap review.
5. Builder applies fixes.
6. Run verification.
7. Commit.
8. Report what changed, how it was verified, and whether the human owner needs to do anything.

The report format should always include:

- what was done
- changed files
- validation results
- next task
- `what you need to do` or `none`

## 9. Handoff Expectations

A handoff is not complete unless all of the following are true:

1. The implementation is committed.
2. `SPEC.md`, `tasks/plan.md`, and `tasks/todo.md` reflect the new state.
3. Contract docs are updated if routes, storage, scopes, or outputs changed.
4. Tests and lint were run, or the reason they were not run is explicitly stated.
5. Critic and reviewer outcomes are recorded honestly.
6. Any blocked external dependency is clearly called out.

Minimum handoff note:

```text
- commit hash and message
- slice summary
- key files changed
- verification results
- critic/reviewer status
- next recommended task
- user action needed: none / required action
```

## 10. When To Ask The Human Owner

Escalate when a slice needs one of these:

- external API keys
- account login or subscription access
- infrastructure changes outside the repo
- a decision that changes product boundaries or persistence contracts
- destructive migration or irreversible data movement

If no action is needed, keep moving to the next planned slice automatically.

## 11. Troubleshooting

### `uv` not found

- use `.\scripts\bootstrap.ps1`
- the helper under `scripts/lib/resolve-uv.ps1` should resolve the command path

### Gemini Pro critic does not complete

- wait and retry first
- if it still does not complete in a reasonable window, use `Codex Critic`
- do not downgrade the critic role to a lower-quality model

### Codex critic or reviewer CLI times out

- attempt the focused command once
- if it still times out, perform an honest in-session critic or reviewer pass
- record that the CLI did not complete

### Readiness fails

Check:

1. `apps/api/.env`
2. storage paths under `data/meta`
3. bootstrap logic in `apps/api/src/knowloop_api/db/bootstrap.py`
4. path derivation in `apps/api/src/knowloop_api/core/config.py`

### Maintenance status looks wrong

Check:

1. the request `course_id` and `class_id`
2. whether `GET /api/v1/maintenance/report` has been run for that scope
3. the scoped file under `data/meta/maintenance/{course_id}/{class_id}/lint-status.json`

## 12. Recommended Next Work

After the current backend state, the next high-value work is:

1. strengthen end-to-end query fixture coverage
2. tighten candidate-to-wiki promotion coverage
3. define the frontend-facing information architecture against the locked backend routes

## 13. Related Documents

- `docs/README.md`
- `docs/architecture/data-contracts.md`
- `docs/architecture/query-writeback-policy.md`
- `docs/architecture/api-contracts.md`
- `docs/architecture/promotion-policy.md`
- `docs/development/agent-harness.md`
- `SPEC.md`
- `tasks/plan.md`
- `tasks/todo.md`
