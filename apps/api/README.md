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

- runtime scaffold
- health endpoints
- config entry point
- test and lint bootstrap

Future work will add:

- storage bootstrap for the knowledge layers
- query and write-back flows
- validator and maintenance services
