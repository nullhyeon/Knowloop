from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from knowloop_api.core.config import Settings
from knowloop_api.db.manifest import load_manifest
from knowloop_api.services.candidates import CandidateStatus, list_candidates
from knowloop_api.services.wiki import list_wiki_pages

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"


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
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    return MaintenanceReport.model_validate(payload)


def save_maintenance_report(settings: Settings, report: MaintenanceReport) -> None:
    report_path = build_maintenance_report_path(
        settings,
        course_id=report.course_id,
        class_id=report.class_id,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            report.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
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
    for candidate in list_candidates(settings, status=CandidateStatus.OPEN):
        if candidate.course_id != course_id or candidate.class_id != class_id:
            continue
        if candidate.created_at.astimezone(UTC) > threshold:
            continue
        age_days = max(0, (now - candidate.created_at.astimezone(UTC)).days)
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
        for candidate in list_candidates(settings)
        if candidate.course_id == course_id and candidate.class_id == class_id
    }
    checks: list[MaintenanceCheck] = []
    for page in list_wiki_pages(settings):
        if page.course_id != course_id or page.class_scope != class_id:
            continue
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
    manifest_source_ids = {source.source_id for source in load_manifest(settings).sources}
    checks: list[MaintenanceCheck] = []
    for page in list_wiki_pages(settings):
        if page.course_id != course_id or page.class_scope != class_id:
            continue
        for source_id in page.source_refs:
            if source_id in manifest_source_ids:
                continue
            checks.append(
                MaintenanceCheck(
                    code="orphan_wiki_source_ref",
                    severity=SEVERITY_ERROR,
                    entity_type="wiki_page",
                    entity_id=page.page_id,
                    message="Wiki page references a source that is missing from the manifest.",
                    details={
                        "missing_source_id": source_id,
                        "path": page.path,
                    },
                )
            )
    return checks
