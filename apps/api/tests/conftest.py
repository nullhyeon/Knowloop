from __future__ import annotations

import os

# Fail closed before test modules import application settings or clients.
os.environ["KNOWLOOP_LLM_ENABLED"] = "false"
os.environ.pop("KNOWLOOP_OPENAI_API_KEY", None)

def pytest_sessionstart(session) -> None:  # noqa: ANN001
    # Keep the local developer .env free to enable live LLM smoke runs while
    # ensuring the automated test suite never makes external API calls.
    os.environ["KNOWLOOP_LLM_ENABLED"] = "false"
    os.environ.pop("KNOWLOOP_OPENAI_API_KEY", None)
