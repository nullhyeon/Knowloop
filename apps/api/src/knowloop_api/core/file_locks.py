from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path


class FileLockBusyError(RuntimeError):
    """Raised when a filesystem lock is held by another active writer."""


def build_file_lock_path(target_path: Path) -> Path:
    digest = hashlib.sha1(str(target_path).encode("utf-8")).hexdigest()[:12]
    return target_path.parent / f".lock-{digest}"


def acquire_file_locks(
    target_paths: Iterable[Path],
    *,
    stale_after: timedelta,
) -> list[Path]:
    lock_paths: list[Path] = []
    try:
        for target_path in sorted({Path(item) for item in target_paths}, key=str):
            lock_paths.append(
                acquire_file_lock(
                    target_path,
                    stale_after=stale_after,
                )
            )
    except Exception:
        release_file_locks(lock_paths)
        raise
    return lock_paths


def acquire_file_lock(
    target_path: Path,
    *,
    stale_after: timedelta,
) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = build_file_lock_path(target_path)
    try:
        _write_lock(lock_path, target_path.name)
    except FileExistsError as exc:
        if not _try_clear_stale_lock(lock_path, stale_after=stale_after):
            raise FileLockBusyError("file storage is busy, retry later") from exc
        try:
            _write_lock(lock_path, target_path.name)
        except FileExistsError as retry_exc:
            raise FileLockBusyError("file storage is busy, retry later") from retry_exc
    return lock_path


def release_file_locks(lock_paths: Iterable[Path]) -> None:
    for lock_path in lock_paths:
        lock_path.unlink(missing_ok=True)


def _write_lock(lock_path: Path, contents: str) -> None:
    with lock_path.open("x", encoding="utf-8") as handle:
        handle.write(contents)


def _try_clear_stale_lock(lock_path: Path, *, stale_after: timedelta) -> bool:
    try:
        modified_at = datetime.fromtimestamp(lock_path.stat().st_mtime, tz=UTC)
    except FileNotFoundError:
        return True

    if datetime.now(UTC) - modified_at <= stale_after:
        return False

    try:
        _unlink_lock(lock_path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def _unlink_lock(lock_path: Path) -> None:
    lock_path.unlink()
