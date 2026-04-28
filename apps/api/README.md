# Knowloop API

This is the backend entry point for Knowloop.

## Commands

```powershell
uv sync
uv run uvicorn knowloop_api.main:app --app-dir src --reload --host 127.0.0.1 --port 8000
uv run pytest
uv run ruff check .
```

## Current Scope

- FastAPI runtime with health and readiness endpoints
- storage bootstrap for `data_root`, manifest, `sessions.db`, and `audit.db`, with service-owned raw source, candidate, wiki, learning, and maintenance storage layers
- signed or legacy-demo request context resolution for role, actor, course, class, and domain scope
- raw source registration and scoped source browsing
- session persistence, recent listing, role-aware search, and instructor insight aggregation
- query response orchestration with replay-safe idempotency, retrieval references, session write-back, candidate creation, and learning-note enrichment
- candidate review, merge/drop/approve flows, wiki promotion, source-integrity preflight, and replay recovery
- maintenance report generation/status, runtime status checks, fixture seeding, body/field bound validation, and audit mutation tracking

Remaining production integration work is outside this backend MVP core: attach the signed-context adapter to a real identity provider, deploy with production secrets, and build the frontend against the documented API contracts.
