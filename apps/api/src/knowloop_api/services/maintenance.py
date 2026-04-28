from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from knowloop_api.core.config import Settings
from knowloop_api.core.frontmatter import parse_frontmatter_document
from knowloop_api.db.manifest import load_manifest
from knowloop_api.services.candidates import (
    CandidateStatus,
    iter_candidates,
)
from knowloop_api.services.sources import resolve_source_path
from knowloop_api.services.wiki import (
    WikiPage,
    build_wiki_page_path,
    load_wiki_page_from_path,
    load_wiki_page_metadata_from_path,
)

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
CORRUPTED_REPORT_CODE = "maintenance_report_unreadable"
NONCANONICAL_WIKI_PAGE_CODE = "noncanonical_wiki_page_path"
INVALID_WIKI_PAGE_CODE = "invalid_wiki_page_metadata"
FRONTMATTER_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class MaintenanceCheck(BaseModel):
    code: str
    severity: Literal["warning", "error"]
    entity_type: str
    entity_id: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class MaintenanceReport(BaseModel):
    version: int = 1
    course_id: str
    class_id: str
    status: str = "not-run"
    last_run_at: datetime | None = None
    health_score: int = 100
    review_queue_count: int = 0
    summary: dict[str, int] = Field(default_factory=dict)
    checks: list[MaintenanceCheck] = Field(default_factory=list)


def build_maintenance_report(
    settings: Settings,
    *,
    course_id: str,
    class_id: str,
    now: datetime | None = None,
    stale_candidate_days: int = 7,
) -> MaintenanceReport:
    reference_time = (now or datetime.now(UTC)).astimezone(UTC)
    checks: list[MaintenanceCheck] = []
    checks.extend(
        _collect_stale_candidate_checks(
            settings,
            course_id=course_id,
            class_id=class_id,
            now=reference_time,
            stale_candidate_days=stale_candidate_days,
        )
    )
    checks.extend(
        _collect_orphan_wiki_candidate_checks(
            settings,
            course_id=course_id,
            class_id=class_id,
        )
    )
    checks.extend(
        _collect_orphan_wiki_source_checks(
            settings,
            course_id=course_id,
            class_id=class_id,
        )
    )
    checks.extend(
        _collect_wiki_layout_checks(
            settings,
            course_id=course_id,
            class_id=class_id,
        )
    )
    checks = sorted(
        checks,
        key=lambda check: (
            0 if check.severity == SEVERITY_ERROR else 1,
            check.code,
            check.entity_type,
            check.entity_id,
        ),
    )

    error_count = sum(1 for check in checks if check.severity == SEVERITY_ERROR)
    warning_count = sum(1 for check in checks if check.severity == SEVERITY_WARNING)
    health_score = max(0, 100 - (error_count * 25) - (warning_count * 10))
    status = "clean"
    if error_count:
        status = "error"
    elif warning_count:
        status = "warning"

    report = MaintenanceReport(
        course_id=course_id,
        class_id=class_id,
        status=status,
        last_run_at=reference_time,
        health_score=health_score,
        review_queue_count=len(checks),
        summary={
            "errors": error_count,
            "warnings": warning_count,
            "stale_candidates": sum(
                1 for check in checks if check.code == "stale_candidate"
            ),
            "orphan_candidate_refs": sum(
                1 for check in checks if check.code == "orphan_wiki_candidate_ref"
            ),
            "orphan_source_refs": sum(
                1 for check in checks if check.code == "orphan_wiki_source_ref"
            ),
            "wiki_layout_issues": sum(
                1
                for check in checks
                if check.code in {NONCANONICAL_WIKI_PAGE_CODE, INVALID_WIKI_PAGE_CODE}
            ),
        },
        checks=checks,
    )
    save_maintenance_report(settings, report)
    return report


def load_maintenance_report(
    settings: Settings,
    *,
    course_id: str,
    class_id: str,
) -> MaintenanceReport:
    report_path = build_maintenance_report_path(
        settings,
        course_id=course_id,
        class_id=class_id,
    )
    if not report_path.exists():
        return MaintenanceReport(course_id=course_id, class_id=class_id)
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        report = MaintenanceReport.model_validate(payload)
        if report.course_id != course_id or report.class_id != class_id:
            raise ValueError("persisted maintenance report scope does not match its path")
        return report
    except (OSError, json.JSONDecodeError, ValidationError):
        return _build_corrupted_maintenance_report(course_id=course_id, class_id=class_id)
    except ValueError:
        return _build_corrupted_maintenance_report(course_id=course_id, class_id=class_id)


def _build_corrupted_maintenance_report(*, course_id: str, class_id: str) -> MaintenanceReport:
    return MaintenanceReport(
        course_id=course_id,
        class_id=class_id,
        status="error",
        health_score=0,
        review_queue_count=1,
        summary={
            "errors": 1,
            "warnings": 0,
            "stale_candidates": 0,
            "orphan_candidate_refs": 0,
            "orphan_source_refs": 0,
            "wiki_layout_issues": 0,
        },
        checks=[
            MaintenanceCheck(
                code=CORRUPTED_REPORT_CODE,
                severity=SEVERITY_ERROR,
                entity_type="maintenance_report",
                entity_id=f"{course_id}:{class_id}",
                message="Persisted maintenance report could not be read.",
                details={},
            )
        ],
    )


def save_maintenance_report(settings: Settings, report: MaintenanceReport) -> None:
    report_path = build_maintenance_report_path(
        settings,
        course_id=report.course_id,
        class_id=report.class_id,
    )
    _write_text_atomically(
        report_path,
        json.dumps(
            report.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )


def build_maintenance_report_path(
    settings: Settings,
    *,
    course_id: str,
    class_id: str,
) -> Path:
    return settings.meta_root / "maintenance" / course_id / class_id / "lint-status.json"


def _collect_stale_candidate_checks(
    settings: Settings,
    *,
    course_id: str,
    class_id: str,
    now: datetime,
    stale_candidate_days: int,
) -> list[MaintenanceCheck]:
    threshold = now - timedelta(days=stale_candidate_days)
    checks: list[MaintenanceCheck] = []
    for candidate in iter_candidates(
        settings,
        status=CandidateStatus.OPEN,
        class_id=class_id,
    ):
        if candidate.course_id != course_id:
            continue
        updated_at = candidate.updated_at.astimezone(UTC)
        if updated_at > threshold:
            continue
        age_days = max(0, (now - updated_at).days)
        checks.append(
            MaintenanceCheck(
                code="stale_candidate",
                severity=SEVERITY_WARNING,
                entity_type="candidate",
                entity_id=candidate.candidate_id,
                message="Open candidate has been waiting beyond the stale threshold.",
                details={
                    "age_days": age_days,
                    "class_id": candidate.class_id,
                    "course_id": candidate.course_id,
                    "kind": candidate.kind.value,
                    "updated_at": updated_at.isoformat().replace("+00:00", "Z"),
                },
            )
        )
    return checks


def _collect_orphan_wiki_candidate_checks(
    settings: Settings,
    *,
    course_id: str,
    class_id: str,
) -> list[MaintenanceCheck]:
    candidate_ids = {
        candidate.candidate_id
        for candidate in iter_candidates(settings, class_id=class_id)
        if candidate.course_id == course_id
    }
    checks: list[MaintenanceCheck] = []
    for page in _load_scoped_wiki_pages(
        settings,
        course_id=course_id,
        class_id=class_id,
    ):
        for candidate_id in page.candidate_refs:
            if candidate_id in candidate_ids:
                continue
            checks.append(
                MaintenanceCheck(
                    code="orphan_wiki_candidate_ref",
                    severity=SEVERITY_ERROR,
                    entity_type="wiki_page",
                    entity_id=page.page_id,
                    message="Wiki page references a candidate that no longer exists.",
                    details={
                        "missing_candidate_id": candidate_id,
                        "path": page.path,
                    },
                )
            )
    return checks


def _collect_orphan_wiki_source_checks(
    settings: Settings,
    *,
    course_id: str,
    class_id: str,
) -> list[MaintenanceCheck]:
    manifest_source_presence = _build_scoped_source_presence_index(
        settings,
        course_id=course_id,
        class_id=class_id,
    )
    checks: list[MaintenanceCheck] = []
    for page in _load_scoped_wiki_pages(
        settings,
        course_id=course_id,
        class_id=class_id,
    ):
        for source_id in page.source_refs:
            if manifest_source_presence.get(source_id):
                continue
            checks.append(
                MaintenanceCheck(
                    code="orphan_wiki_source_ref",
                    severity=SEVERITY_ERROR,
                    entity_type="wiki_page",
                    entity_id=page.page_id,
                    message=(
                        "Wiki page references a source that is no longer available "
                        "in the current source store."
                    ),
                    details={
                        "missing_source_id": source_id,
                        "path": page.path,
                    },
                )
            )
    return checks


def maintenance_report_to_status_payload(
    report: MaintenanceReport,
    *,
    include_sensitive_checks: bool,
) -> dict[str, object]:
    payload = report.model_dump(mode="json", exclude_none=True)
    if include_sensitive_checks:
        return payload

    payload["checks"] = [
        {
            "code": check.code,
            "severity": check.severity,
            "entity_type": check.entity_type,
            "summary": _public_summary_for_check(check),
        }
        for check in report.checks
    ]
    return payload


def _public_summary_for_check(check: MaintenanceCheck) -> str:
    summaries = {
        CORRUPTED_REPORT_CODE: "The saved maintenance report could not be read.",
        "stale_candidate": "An open candidate has been waiting longer than the stale threshold.",
        "orphan_wiki_candidate_ref": (
            "A wiki page references a candidate that is no longer available."
        ),
        "orphan_wiki_source_ref": "A wiki page references a source that is no longer available.",
        NONCANONICAL_WIKI_PAGE_CODE: (
            "A wiki page is stored outside the canonical class-scoped path and needs migration."
        ),
        INVALID_WIKI_PAGE_CODE: (
            "A wiki page has invalid metadata and needs repair before it can be indexed."
        ),
    }
    return summaries.get(check.code, "Maintenance check requires follow-up.")


def _build_scoped_source_presence_index(
    settings: Settings,
    *,
    course_id: str,
    class_id: str,
) -> dict[str, bool]:
    presence: dict[str, bool] = {}
    for source in load_manifest(settings).sources:
        if source.course_id != course_id or source.class_id != class_id:
            continue
        try:
            presence[source.source_id] = resolve_source_path(
                settings,
                source.origin_path,
            ).is_file()
        except ValueError:
            presence[source.source_id] = False
    return presence


def _load_scoped_wiki_pages(
    settings: Settings,
    *,
    course_id: str,
    class_id: str,
) -> list[WikiPage]:
    wiki_root = settings.data_root / "wiki"
    if not wiki_root.exists():
        return []

    pages: list[WikiPage] = []
    for domain_root in sorted(path for path in wiki_root.iterdir() if path.is_dir()):
        scoped_root = domain_root / class_id
        if not scoped_root.is_dir():
            continue
        for path in sorted(scoped_root.glob("*.md")):
            try:
                page = load_wiki_page_metadata_from_path(path)
                canonical_path = build_wiki_page_path(
                    settings,
                    domain=page.domain,
                    class_scope=page.class_scope,
                    page_id=page.page_id,
                ).resolve()
            except (KeyError, OSError, ValueError):
                continue
            if path.resolve() != canonical_path:
                continue
            if page.course_id != course_id or page.class_scope != class_id:
                continue
            pages.append(page)
    return pages


def _collect_wiki_layout_checks(
    settings: Settings,
    *,
    course_id: str,
    class_id: str,
) -> list[MaintenanceCheck]:
    wiki_root = settings.data_root / "wiki"
    if not wiki_root.exists():
        return []

    checks: list[MaintenanceCheck] = []
    for path in sorted(wiki_root.glob("**/*.md")):
        if path.name.startswith("."):
            continue

        try:
            page = load_wiki_page_from_path(path)
        except (KeyError, OSError, ValueError) as exc:
            metadata = _read_wiki_frontmatter_metadata(path)
            if not _wiki_file_belongs_to_scope(
                path,
                metadata=metadata,
                course_id=course_id,
                class_id=class_id,
            ):
                continue
            checks.append(
                MaintenanceCheck(
                    code=INVALID_WIKI_PAGE_CODE,
                    severity=SEVERITY_ERROR,
                    entity_type="wiki_page",
                    entity_id=str(metadata.get("page_id") or path.as_posix()),
                    message=(
                        "Wiki page file in the current scope could not be parsed into a "
                        "canonical page record."
                    ),
                    details={
                        "path": path.as_posix(),
                        "reason": str(exc),
                    },
                )
            )
            continue

        if page.course_id != course_id or page.class_scope != class_id:
            if _wiki_file_path_belongs_to_class(path, class_id=class_id):
                reason_parts: list[str] = []
                if page.course_id != course_id:
                    reason_parts.append(
                        f"course_id points to {page.course_id!r} instead of {course_id!r}"
                    )
                if page.class_scope != class_id:
                    reason_parts.append(
                        f"class_scope points to {page.class_scope!r} instead of {class_id!r}"
                    )
                checks.append(
                    MaintenanceCheck(
                        code=INVALID_WIKI_PAGE_CODE,
                        severity=SEVERITY_ERROR,
                        entity_type="wiki_page",
                        entity_id=page.page_id,
                        message=(
                            "Wiki page file lives inside the current class path but its metadata "
                            "points to a different scope."
                        ),
                        details={
                            "path": path.as_posix(),
                            "reason": "; ".join(reason_parts),
                        },
                    )
                )
                continue
            if not _wiki_file_belongs_to_scope(
                path,
                metadata={
                    "course_id": page.course_id,
                    "class_scope": page.class_scope,
                },
                course_id=course_id,
                class_id=class_id,
            ):
                continue
            if page.class_scope != class_id:
                continue
        path_class_scope = _wiki_file_path_class_scope(path)
        if path_class_scope is not None and path_class_scope != class_id:
            continue

        try:
            canonical_path = build_wiki_page_path(
                settings,
                domain=page.domain,
                class_scope=page.class_scope,
                page_id=page.page_id,
            ).resolve()
        except ValueError as exc:
            checks.append(
                MaintenanceCheck(
                    code=INVALID_WIKI_PAGE_CODE,
                    severity=SEVERITY_ERROR,
                    entity_type="wiki_page",
                    entity_id=page.page_id,
                    message=(
                        "Wiki page metadata does not satisfy the canonical "
                        "page_id/domain contract."
                    ),
                    details={
                        "path": path.as_posix(),
                        "reason": str(exc),
                    },
                )
            )
            continue

        resolved_path = path.resolve()
        if resolved_path == canonical_path:
            continue

        checks.append(
            MaintenanceCheck(
                code=NONCANONICAL_WIKI_PAGE_CODE,
                severity=SEVERITY_ERROR,
                entity_type="wiki_page",
                entity_id=page.page_id,
                message="Wiki page is stored outside the canonical class-scoped path.",
                details={
                    "path": path.as_posix(),
                    "canonical_path": canonical_path.as_posix(),
                },
            )
        )
    return checks


def _read_wiki_frontmatter_metadata(path: Path) -> dict[str, object]:
    try:
        contents = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return _read_wiki_frontmatter_metadata_prefix(path)
    try:
        metadata, _ = parse_frontmatter_document(contents)
    except ValueError:
        return _parse_partial_frontmatter_metadata(contents)
    if metadata:
        return metadata
    if contents.startswith("---"):
        return _parse_partial_frontmatter_metadata(contents)
    return metadata


def _read_wiki_frontmatter_metadata_prefix(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as handle:
            first_line = handle.readline()
            if first_line.strip() != b"---":
                return {}
            frontmatter_lines = [first_line]
            for line in handle:
                frontmatter_lines.append(line)
                if line.strip() == b"---":
                    break
            else:
                return {}
        contents = b"".join(frontmatter_lines).decode("utf-8")
    except (OSError, UnicodeError):
        return {}

    try:
        metadata, _ = parse_frontmatter_document(contents)
    except ValueError:
        return _parse_partial_frontmatter_metadata(contents)
    if metadata:
        return metadata
    return _parse_partial_frontmatter_metadata(contents)


def _wiki_file_belongs_to_scope(
    path: Path,
    *,
    metadata: dict[str, object],
    course_id: str,
    class_id: str,
) -> bool:
    path_class_scope = _wiki_file_path_class_scope(path)
    if path_class_scope is not None:
        return path_class_scope == class_id

    metadata_course_id = metadata.get("course_id")
    metadata_class_scope = metadata.get("class_scope")
    if metadata_class_scope is not None:
        if metadata_class_scope != class_id:
            return False
        if metadata_course_id is not None and metadata_course_id != course_id:
            return False
        return True
    if metadata_course_id is not None:
        return False
    return False


def _wiki_file_path_belongs_to_class(path: Path, *, class_id: str) -> bool:
    return _wiki_file_path_class_scope(path) == class_id


def _wiki_file_path_class_scope(path: Path) -> str | None:
    parts = path.parts
    for index in range(len(parts) - 1, -1, -1):
        part = parts[index]
        if part != "wiki":
            continue
        remaining = parts[index + 1 :]
        if len(remaining) >= 3:
            return remaining[1]
        return None
    return None


def _parse_partial_frontmatter_metadata(contents: str) -> dict[str, object]:
    if not contents.startswith("---"):
        return {}

    lines = contents.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    frontmatter_lines: list[str] = []
    saw_explicit_closing_marker = False
    saw_invalid_line = False
    for line in lines[1:]:
        if line.strip() == "---":
            saw_explicit_closing_marker = True
            break
        if not line.strip():
            break
        if line.startswith(("#", "- ", "* ", "```")):
            break
        if ":" not in line:
            saw_invalid_line = True
            continue
        key, _ = line.split(":", maxsplit=1)
        key = key.strip()
        if not key or FRONTMATTER_KEY_PATTERN.fullmatch(key) is None:
            saw_invalid_line = True
            continue
        frontmatter_lines.append(line)

    if not saw_explicit_closing_marker:
        if not frontmatter_lines:
            return {}
        first_key, _ = frontmatter_lines[0].split(":", maxsplit=1)
        first_key = first_key.strip()
        if first_key != "page_id":
            return {}
    if saw_invalid_line and not saw_explicit_closing_marker:
        return {}

    metadata: dict[str, object] = {}
    for line in frontmatter_lines:
        stripped = line.strip()
        if not stripped or ":" not in line:
            continue
        key, raw_value = line.split(":", maxsplit=1)
        key = key.strip()
        raw_value = raw_value.strip()
        if not raw_value:
            continue
        if (
            raw_value.startswith(('"', "'"))
            and raw_value.endswith(('"', "'"))
            and len(raw_value) >= 2
        ):
            metadata[key] = raw_value[1:-1]
        else:
            metadata[key] = raw_value
    return metadata


def _write_text_atomically(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".tmp-{uuid.uuid4().hex[:8]}"
    temp_path.write_text(contents, encoding="utf-8")
    temp_path.replace(path)
