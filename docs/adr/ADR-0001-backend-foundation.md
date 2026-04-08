# ADR-0001: Backend Foundation and Agent Harness

## Status

Accepted

## Context

Knowloop starts as a backend-first educational memory system. The product needs strong traceability, small verifiable implementation slices, and a shared operating model across Codex and Gemini.

## Decision

We will:

- use a single FastAPI backend as the first runtime
- keep knowledge artifacts as files under `data/`
- use SQLite / FTS5 for indexed retrieval in the MVP
- install `agent-skills` locally under `.agents/`
- make `AGENTS.md` the canonical instruction file
- use `GEMINI.md` only as a Gemini supplement
- keep `SPEC.md`, `tasks/plan.md`, and `tasks/todo.md` as living project artifacts

## Consequences

### Positive

- low setup cost
- easy local demo path
- shared workflow for Codex and Gemini
- reduced ambiguity for future agents

### Negative

- some duplication between file-based artifacts and future database indexes
- future migration work if we outgrow SQLite / FTS5
- frontend remains intentionally deferred until backend contracts are stable

## Follow-Up

- define storage contracts for each knowledge layer
- bootstrap SQLite indexes
- add promotion and maintenance rules
