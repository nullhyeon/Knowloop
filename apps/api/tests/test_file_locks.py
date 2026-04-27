from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import knowloop_api.core.file_locks as file_locks
from knowloop_api.core.file_locks import (
    FileLockBusyError,
    acquire_file_lock,
    build_file_lock_path,
)


def test_file_lock_treats_unreclaimable_stale_lock_as_busy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_path = tmp_path / "target.json"
    lock_path = build_file_lock_path(target_path)
    lock_path.write_text(target_path.name, encoding="utf-8")
    stale_timestamp = (datetime.now(UTC) - timedelta(minutes=10)).timestamp()
    os.utime(lock_path, (stale_timestamp, stale_timestamp))

    def blocked_unlink(path: Path) -> None:
        if path == lock_path:
            raise PermissionError("lock still held")
        path.unlink()

    monkeypatch.setattr(file_locks, "_unlink_lock", blocked_unlink)

    with pytest.raises(FileLockBusyError, match="file storage is busy"):
        acquire_file_lock(target_path, stale_after=timedelta(minutes=5))

    assert lock_path.exists()
