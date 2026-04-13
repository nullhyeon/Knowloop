from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from knowloop_api.core.config import REPO_ROOT, Settings, get_settings
from knowloop_api.core.contracts import (
    ActorRole,
    RequestDomain,
    SourceType,
    allowed_domains_for_source_type,
)
from knowloop_api.core.frontmatter import build_frontmatter_document, parse_frontmatter_document
from knowloop_api.db.audit import create_audit_event
from knowloop_api.db.bootstrap import bootstrap_storage
from knowloop_api.db.manifest import RawSourceRecord, upsert_source_record
from knowloop_api.services.candidates import CandidateItem, create_candidate
from knowloop_api.services.context_profiles import list_context_profiles
from knowloop_api.services.learning import LearningNote, upsert_learning_note
from knowloop_api.services.maintenance import build_maintenance_report
from knowloop_api.services.sessions import SessionRecord, save_session
from knowloop_api.services.sources import (
    build_checksum,
    build_origin_path,
    resolve_source_path,
)
from knowloop_api.services.wiki import build_wiki_page_path

DEFAULT_DEMO_FIXTURE_ROOT = REPO_ROOT / "data" / "fixtures" / "demo"
DEMO_SYSTEM_ACTOR_ID = "system-demo-seed"


@dataclass(slots=True)
class DemoSeedSummary:
    course_id: str
    class_id: str
    source_count: int
    wiki_page_count: int
    session_count: int
    learning_note_count: int
    candidate_count: int
    maintenance_status: str
    maintenance_health_score: int

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


def seed_demo_runtime(
    settings: Settings,
    *,
    fixture_root: Path | None = None,
    allow_destructive_reset: bool = False,
) -> DemoSeedSummary:
    resolved_fixture_root = (fixture_root or DEFAULT_DEMO_FIXTURE_ROOT).resolve()
    _assert_demo_fixture_root(resolved_fixture_root)
    _assert_demo_reset_is_allowed(
        settings,
        fixture_root=resolved_fixture_root,
        allow_destructive_reset=allow_destructive_reset,
    )

    _reset_runtime_storage(settings)
    bootstrap_storage(settings)

    role_actor_ids = _build_role_actor_index(settings)
    source_count = _seed_sources(
        settings,
        fixtures_root=resolved_fixture_root / "sources",
        role_actor_ids=role_actor_ids,
    )
    wiki_page_count = _seed_wiki_pages(
        settings,
        fixtures_root=resolved_fixture_root / "wiki",
    )
    session_count = _seed_sessions(
        settings,
        fixtures_root=resolved_fixture_root / "sessions",
    )
    learning_note_count = _seed_learning_notes(
        settings,
        fixtures_root=resolved_fixture_root / "learning",
    )
    candidate_count = _seed_candidates(
        settings,
        fixtures_root=resolved_fixture_root / "candidates",
    )

    course_id, class_id = _resolve_demo_scope(settings)
    maintenance_report = build_maintenance_report(
        settings,
        course_id=course_id,
        class_id=class_id,
    )

    return DemoSeedSummary(
        course_id=course_id,
        class_id=class_id,
        source_count=source_count,
        wiki_page_count=wiki_page_count,
        session_count=session_count,
        learning_note_count=learning_note_count,
        candidate_count=candidate_count,
        maintenance_status=maintenance_report.status,
        maintenance_health_score=maintenance_report.health_score,
    )


def _assert_demo_fixture_root(fixtures_root: Path) -> None:
    if not fixtures_root.exists():
        raise FileNotFoundError(f"demo fixture root was not found: {fixtures_root}")


def _assert_demo_reset_is_allowed(
    settings: Settings,
    *,
    fixture_root: Path,
    allow_destructive_reset: bool,
) -> None:
    if allow_destructive_reset:
        _assert_demo_data_root(settings.data_root)
        return
    raise RuntimeError(
        "seed_demo_runtime refused to reset mutable runtime storage without "
        "allow_destructive_reset=True. This command wipes wiki, learning, "
        "candidate, raw, session, and maintenance data under "
        f"{settings.data_root} using demo fixtures from {fixture_root}."
    )


def _assert_demo_data_root(data_root: Path) -> None:
    allowed_markers = ("demo", "sample", "sandbox")
    normalized_parts = [part.lower() for part in data_root.parts]
    if any(marker in part for part in normalized_parts for marker in allowed_markers):
        return
    raise RuntimeError(
        "seed_demo_runtime refused to reset mutable runtime storage because "
        f"{data_root} does not look like an isolated demo data root. Choose a "
        "path containing 'demo', 'sample', or 'sandbox'."
    )


def _reset_runtime_storage(settings: Settings) -> None:
    directories_to_reset = [
        settings.data_root / "wiki",
        settings.data_root / "learning",
        settings.data_root / "candidate",
        settings.data_root / "raw",
        settings.data_root / "sessions",
        settings.meta_root / "maintenance",
    ]
    files_to_remove = [
        settings.meta_root / "manifest.json",
        settings.sessions_db_path,
        settings.audit_db_path,
    ]

    for directory in directories_to_reset:
        shutil.rmtree(directory, ignore_errors=True)
    for file_path in files_to_remove:
        file_path.unlink(missing_ok=True)


def _build_role_actor_index(settings: Settings) -> dict[ActorRole, str]:
    actor_ids: dict[ActorRole, str] = {}
    for profile in list_context_profiles(settings):
        actor_ids.setdefault(profile.role, profile.actor_id)
    actor_ids.setdefault(ActorRole.SYSTEM, DEMO_SYSTEM_ACTOR_ID)
    return actor_ids


def _seed_sources(
    settings: Settings,
    *,
    fixtures_root: Path,
    role_actor_ids: dict[ActorRole, str],
) -> int:
    source_count = 0
    for fixture_path in sorted(fixtures_root.glob("*.md")):
        metadata, body = parse_frontmatter_document(_read_fixture_text(fixture_path))
        source_type = SourceType(str(metadata["source_type"]))
        actor_role = ActorRole(str(metadata["actor_role"]))
        created_at = _parse_timestamp(str(metadata["created_at"]))
        domain = _resolve_source_domain_from_fixture(metadata, source_type=source_type)
        actor_id = role_actor_ids.get(actor_role)

        source_record = RawSourceRecord(
            source_id=str(metadata["source_id"]),
            source_type=source_type,
            domain=domain,
            title=str(metadata["title"]),
            class_id=str(metadata["class_id"]),
            course_id=str(metadata["course_id"]),
            actor_role=actor_role,
            created_at=created_at,
            origin_path=build_origin_path(
                source_type,
                class_id=str(metadata["class_id"]),
                domain=domain,
                source_id=str(metadata["source_id"]),
                filename=fixture_path.name,
                mime_type="text/markdown",
            ),
            checksum=build_checksum(body),
            status="registered",
            uploaded_by=actor_id,
            mime_type="text/markdown",
            filename=fixture_path.name,
            tags=_derive_source_tags(title=str(metadata["title"]), source_type=source_type),
            summary=_extract_markdown_summary(body),
        )
        source_path = resolve_source_path(settings, source_record.origin_path)
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(body, encoding="utf-8")
        upsert_source_record(settings, source_record)
        create_audit_event(
            settings,
            entity_type="source",
            entity_id=source_record.source_id,
            action="source_registered",
            actor_role=actor_role.value,
            actor_id=actor_id,
            to_status=source_record.status,
            notes=f"Seeded demo source from {fixture_path.name}.",
            created_at=created_at,
        )
        source_count += 1
    return source_count


def _seed_wiki_pages(
    settings: Settings,
    *,
    fixtures_root: Path,
) -> int:
    page_count = 0
    for fixture_path in sorted(fixtures_root.glob("*.md")):
        metadata, body = parse_frontmatter_document(_read_fixture_text(fixture_path))
        target_path = build_wiki_page_path(
            settings,
            domain=str(metadata["domain"]),
            class_scope=str(metadata["class_scope"]),
            page_id=str(metadata["page_id"]),
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            build_frontmatter_document(metadata, body),
            encoding="utf-8",
        )
        page_count += 1
    return page_count


def _seed_sessions(
    settings: Settings,
    *,
    fixtures_root: Path,
) -> int:
    session_count = 0
    for fixture_path in sorted(fixtures_root.glob("*.json")):
        payload = json.loads(_read_fixture_text(fixture_path))
        for item in payload:
            session = SessionRecord.model_validate(item)
            save_session(
                settings,
                session,
                details={"seed_fixture": fixture_path.name},
                request_id=f"seed-{fixture_path.stem}-{session.session_id}",
            )
            session_count += 1
    return session_count


def _seed_learning_notes(
    settings: Settings,
    *,
    fixtures_root: Path,
) -> int:
    note_count = 0
    for fixture_path in sorted(fixtures_root.glob("*.json")):
        note = LearningNote.model_validate(
            json.loads(_read_fixture_text(fixture_path))
        )
        upsert_learning_note(
            settings,
            note,
            actor_id=DEMO_SYSTEM_ACTOR_ID,
            request_id=f"seed-{fixture_path.stem}",
            notes=f"Seeded demo learning note from {fixture_path.name}.",
        )
        note_count += 1
    return note_count


def _seed_candidates(
    settings: Settings,
    *,
    fixtures_root: Path,
) -> int:
    candidate_count = 0
    for fixture_path in sorted(fixtures_root.glob("*.json")):
        candidate = CandidateItem.model_validate(
            json.loads(_read_fixture_text(fixture_path))
        )
        actor_role = candidate.actor_role or ActorRole.SYSTEM
        create_candidate(
            settings,
            candidate,
            actor_role=actor_role,
            actor_id=DEMO_SYSTEM_ACTOR_ID if actor_role is ActorRole.SYSTEM else None,
            request_id=f"seed-{fixture_path.stem}",
            notes=f"Seeded demo candidate from {fixture_path.name}.",
        )
        candidate_count += 1
    return candidate_count


def _resolve_source_domain_from_fixture(
    metadata: dict[str, object],
    *,
    source_type: SourceType,
) -> RequestDomain:
    if "domain" in metadata:
        return RequestDomain(str(metadata["domain"]))

    if source_type is SourceType.ANNOUNCEMENT:
        source_id = str(metadata["source_id"])
        if source_id.startswith("src-announcement-ops-"):
            return RequestDomain.OPERATIONS
        return RequestDomain.ACADEMIC

    allowed_domains = allowed_domains_for_source_type(source_type)
    if len(allowed_domains) != 1:
        raise ValueError(f"fixture is missing domain for flexible source type: {source_type.value}")
    return next(iter(allowed_domains))


def _derive_source_tags(*, title: str, source_type: SourceType) -> list[str]:
    normalized_title = title.lower()
    derived_tags = [source_type.value.replace("_", "-")]
    for token in ("chain rule", "product rule", "homework", "deadline", "refund"):
        if token in normalized_title:
            derived_tags.append(token.replace(" ", "-"))
    return derived_tags


def _extract_markdown_summary(body: str) -> str | None:
    for block in body.split("\n\n"):
        normalized = " ".join(line.strip() for line in block.splitlines() if line.strip())
        if not normalized:
            continue
        if normalized.startswith("#"):
            continue
        if normalized.startswith("- "):
            continue
        return normalized[:220]
    return None


def _resolve_demo_scope(settings: Settings) -> tuple[str, str]:
    profiles = list_context_profiles(settings)
    for profile in profiles:
        if profile.profile_id == "student-minji":
            return profile.course_id, profile.class_id
    if not profiles:
        raise RuntimeError("no context profiles are available to resolve demo scope")
    return profiles[0].course_id, profiles[0].class_id


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _read_fixture_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _build_settings_from_args(args: argparse.Namespace) -> Settings:
    if args.data_root is None:
        return get_settings()
    return Settings(data_root=Path(args.data_root))


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reset mutable runtime storage and seed deployment-ready demo data.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Optional override for KNOWLOOP_DATA_ROOT.",
    )
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=DEFAULT_DEMO_FIXTURE_ROOT,
        help="Location of the deployment demo fixtures.",
    )
    parser.add_argument(
        "--allow-destructive-reset",
        action="store_true",
        help="Required safety gate for wiping mutable runtime storage before seeding demo data.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    settings = _build_settings_from_args(args)
    summary = seed_demo_runtime(
        settings,
        fixture_root=Path(args.fixture_root),
        allow_destructive_reset=args.allow_destructive_reset,
    )
    print(json.dumps(summary.to_payload(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
