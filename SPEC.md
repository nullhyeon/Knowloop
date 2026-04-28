# Spec: Knowloop Backend MVP Core

## Objective

Build the backend core for Knowloop, an education-focused memory OS that converts educational interactions into persistent, queryable knowledge layers.

The backend MVP core is implemented enough for frontend work to begin. The current priority is to keep the executable backend contracts accurate while frontend integration and production hardening proceed:

- preserve reproducible bootstrap for `sessions.db`, `audit.db`, and manifest storage, plus service-owned raw source, candidate, wiki, learning, maintenance, and fixture data layers
- keep storage and APIs aligned with the planning documents
- maintain the running `query -> session -> candidate -> review -> wiki/learning` flow
- keep the dedicated `wiki` read surface stable
- keep the instructor insight surface aggregated and privacy-safe
- keep the session search surface role-aware and redaction-safe
- support the frontend-ready context bootstrap adapter for local demo personas
- require production deployments to use a trusted signed-context adapter instead of accepting forgeable role/scope headers
- keep the maintenance report surface actionable and deterministic
- keep the reproducible offline backend smoke suite and opt-in live LLM smoke current
- document operational runbook and handoff expectations for the current backend state
- preserve query fixture coverage around answer basis, retrieval refs, replay recovery, and write-back outputs
- preserve declarative follow-up and error query fixtures with setup validation
- preserve candidate-to-wiki promotion replay coverage across approve, merge, and drop mutations

Primary users for this backend spec:

- AI coding agents working in the repo
- the human owner coordinating backend delivery

Success at this stage means:

- the planning documents and backend docs match the implemented code-facing contracts
- storage bootstrap is reproducible
- fixture-based tests and smoke scripts verify the backend surface
- the API can evolve from stable route and schema contracts without breaking the review, wiki, instructor, session-search, and maintenance workflows

## Tech Stack

- Python 3.12
- FastAPI
- `uv` for project and command execution
- `pytest` for tests
- `ruff` for linting
- SQLite / FTS5 for MVP storage
- Markdown files under `data/` for wiki-like artifacts

## Commands

All commands are run from the repository root unless noted.

```powershell
# bootstrap backend dependencies
.\scripts\bootstrap.ps1

# run local API
.\scripts\dev-api.ps1

# run tests
.\scripts\test-api.ps1

# run lint
.\scripts\lint-api.ps1
```

Equivalent direct commands:

```powershell
cd apps/api
uv sync
uv run uvicorn knowloop_api.main:app --app-dir src --reload --host 127.0.0.1 --port 8000
uv run pytest
uv run ruff check .
```

## Project Structure

```text
apps/api/                 Backend runtime and tests
data/                     Raw, session, candidate, wiki, learning, and meta layers
docs/                     Product, architecture, and harness documentation
.agents/                  Local skill library, personas, and prompts
.gemini/                  Gemini project settings
schemas/                  Structured output contracts for agent-generated artifacts
scripts/                  Reproducible PowerShell entrypoints
tasks/                    Living implementation plan and todo list
```

## Planning Contracts To Follow

All backend work must follow these documents before guessing:

- `docs/README.md`
- `docs/architecture/data-contracts.md`
- `docs/architecture/query-writeback-policy.md`
- `docs/architecture/api-contracts.md`
- `docs/architecture/promotion-policy.md`
- `docs/product/role-permissions.md`
- `docs/product/fixture-catalog.md`

## Code Style

Prefer boring, explicit Python with clear names and small functions.

```python
def build_health_payload(environment: str) -> dict[str, str]:
    return {
        "status": "ok",
        "environment": environment,
    }
```

Conventions:

- keep modules small and single-purpose
- prefer typed functions and Pydantic-backed config
- avoid hidden magic or premature abstractions
- document architectural decisions in ADRs rather than long inline comments

## Testing Strategy

- `pytest` for unit and integration tests
- every backend slice should add or update tests

Current verification bar:

- `sessions.db` bootstrap can run on a clean workspace
- `audit.db` bootstrap can run on a clean workspace
- fixture directories and seed inputs are repository-safe
- storage helpers respect the ID and metadata contracts from docs
- health and readiness endpoints respond at both top-level and versioned system routes
- context, source registration, query, search, review, wiki, runtime status, and maintenance routes are covered by integration tests
- the offline smoke suite proves representative context, source registration, query, search, review, wiki, runtime status, and maintenance routes together
- the optional live LLM smoke verifies the OpenAI rewrite path with local runtime settings
- public API boundaries enforce bounded request bodies, idempotency headers, and high-volume text/list fields before storage writes

## Boundaries

### Always

- keep `AGENTS.md`, `SPEC.md`, and `tasks/` aligned with the code
- preserve source traceability and knowledge-layer separation
- use skills and verification for any non-trivial change

### Ask first

- changing the backend framework
- adding new infrastructure services
- introducing full user auth, queues, workers, or vector search
- changing the persisted data contract in a way that invalidates current docs

### Never

- skip the `candidate` stage for unverified knowledge
- commit secrets or private educational data
- fake verification results
- treat chat history as the source of truth instead of repo files

## Success Criteria

- [x] `.agents/skills`, `.agents/agents`, and `.agents/references` are present
- [x] `AGENTS.md` and `GEMINI.md` are configured for Codex and Gemini
- [x] backend scaffold exists under `apps/api`
- [x] backend bootstrap, test, and lint commands are documented and runnable
- [x] backend tests pass
- [x] `tasks/plan.md` and `tasks/todo.md` define the backend slices
- [x] planning contract docs are reflected in `schemas/`
- [x] fixture catalog is reflected in `data/fixtures/`
- [x] storage bootstrap is verified from fixture-driven tests

## Resolved Backend Decisions

- Raw sources are owned by the manifest record plus backing file on disk.
- Sessions and audit/mutation state are owned by SQLite.
- Candidate metadata is owned by JSON files in candidate storage.
- Wiki pages are owned by Markdown files under `data/wiki`.
- Promotion rules are enforced in the review service using the architecture and promotion-policy docs as the contract source.

## Open Questions

- Which external identity provider or session model should replace the signed-context adapter when Knowloop moves beyond MVP deployment boundaries?
