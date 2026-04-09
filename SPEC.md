# Spec: Knowloop Backend MVP Core

## Objective

Build the backend core for Knowloop, an education-focused memory OS that converts educational interactions into persistent, queryable knowledge layers.

The current slice is still not the full product. The harness and runtime foundation already exist. The current priority is to turn the locked planning set into executable backend contracts:

- bootstrap `sessions.db` and `audit.db`
- implement repository-safe fixture seeding
- align storage and APIs with the planning documents
- consolidate the running `query -> session -> candidate -> review` flow and prepare the next dedicated wiki and instructor read surfaces

Primary users for the current slice:

- AI coding agents working in the repo
- the human owner coordinating backend delivery

Success at this stage means:

- the planning documents have been converted into code-facing contracts
- storage bootstrap is reproducible
- fixture-based tests can drive the first backend slices
- the API can evolve from stable route and schema contracts without breaking the review workflow

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

All backend work in the current slice must follow these documents before guessing:

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
- start with app boot and contract tests
- add storage bootstrap and fixture seeding tests before implementing richer ingestion logic
- every backend slice should add or update tests

Current minimum bar:

- API process boots
- `/healthz` responds
- `/api/v1/system/health` responds

Current slice verification bar:

- `sessions.db` bootstrap can run on a clean workspace
- `audit.db` bootstrap can run on a clean workspace
- fixture directories and seed inputs are repository-safe
- storage helpers respect the ID and metadata contracts from docs

## Boundaries

### Always

- keep `AGENTS.md`, `SPEC.md`, and `tasks/` aligned with the code
- preserve source traceability and knowledge-layer separation
- use skills and verification for any non-trivial change

### Ask first

- changing the backend framework
- adding new infrastructure services
- introducing auth, queues, workers, or vector search
- changing the persisted data contract in a way that invalidates current docs

### Never

- skip the `candidate` stage for unverified knowledge
- commit secrets or private educational data
- fake verification results
- treat chat history as the source of truth instead of repo files

## Success Criteria

- [ ] `.agents/skills`, `.agents/agents`, and `.agents/references` are present
- [ ] `AGENTS.md` and `GEMINI.md` are configured for Codex and Gemini
- [ ] backend scaffold exists under `apps/api`
- [ ] backend bootstrap, test, and lint commands are documented and runnable
- [ ] initial backend tests pass
- [ ] `tasks/plan.md` and `tasks/todo.md` define the next backend slices
- [ ] planning contract docs are reflected in `schemas/`
- [ ] fixture catalog is reflected in `data/fixtures/`
- [ ] storage bootstrap can be verified from fixture-driven tests

## Open Questions

- Which persistence layer should own candidate metadata first: plain files, SQLite tables, or a hybrid file-plus-index approach?
- Should promotion rules live in code, config, or markdown policy files?
- At what point should auth and privacy controls move from repo conventions into product code?
