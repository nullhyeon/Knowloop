from __future__ import annotations

import sqlite3
from pathlib import Path

SQLITE_BUSY_TIMEOUT_MS = 5_000
SQLITE_CONNECTION_TIMEOUT_SECONDS = SQLITE_BUSY_TIMEOUT_MS / 1_000
SQLITE_JOURNAL_MODE = "WAL"


def connect_sqlite(
    path: Path,
    *,
    apply_journal_mode: bool = True,
) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS)
    configure_sqlite_connection(connection, apply_journal_mode=apply_journal_mode)
    return connection


def configure_sqlite_connection(
    connection: sqlite3.Connection,
    *,
    apply_journal_mode: bool = True,
) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    if apply_journal_mode:
        connection.execute(f"PRAGMA journal_mode = {SQLITE_JOURNAL_MODE}")
