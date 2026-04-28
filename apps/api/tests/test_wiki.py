import hashlib
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole
from knowloop_api.main import create_app
from knowloop_api.services.wiki import search_wiki_pages

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "data" / "fixtures"


def build_settings(tmp_path: Path) -> Settings:
    digest = hashlib.sha1(str(tmp_path).encode("utf-8")).hexdigest()[:10]
    data_root = Path(tempfile.gettempdir()) / "kl" / digest
    shutil.rmtree(data_root, ignore_errors=True)
    return Settings(data_root=data_root)


def build_client(tmp_path: Path) -> tuple[TestClient, Settings]:
    settings = build_settings(tmp_path)
    return TestClient(create_app(settings), raise_server_exceptions=False), settings


def build_headers(
    *,
    role: str,
    actor_id: str,
    course_id: str = "course-calculus-1",
    class_id: str = "class-calculus-1-2026-spring-a",
    request_id: str = "req-test-wiki",
    domain: str | None = None,
) -> dict[str, str]:
    resolved_domain = domain
    if resolved_domain is None:
        resolved_domain = {
            "student": "academic",
            "instructor": "academic",
            "operator": "operations",
            "validator": "review",
        }.get(role)
    headers = {
        "X-Knowloop-Role": role,
        "X-Knowloop-Actor-Id": actor_id,
        "X-Knowloop-Course-Id": course_id,
        "X-Knowloop-Class-Id": class_id,
        "X-Request-Id": request_id,
    }
    if resolved_domain is not None:
        headers["X-Knowloop-Domain"] = resolved_domain
    return headers


def seed_wiki_fixture(
    settings: Settings,
    *,
    fixture_name: str,
    target_relative_path: str,
    replacements: dict[str, str] | None = None,
) -> None:
    target_path = settings.data_root / Path(target_relative_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    contents = (FIXTURE_ROOT / "wiki" / fixture_name).read_text(encoding="utf-8")
    for original, updated in (replacements or {}).items():
        contents = contents.replace(original, updated)
    target_path.write_text(contents, encoding="utf-8")


def seed_fixture_pack(settings: Settings) -> None:
    seed_wiki_fixture(
        settings,
        fixture_name="concepts-chain-rule.seed.md",
        target_relative_path="wiki/concepts/class-calculus-1-2026-spring-a/chain-rule.md",
    )
    seed_wiki_fixture(
        settings,
        fixture_name="faq-homework-submission.after.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-a/homework-submission.md",
    )
    seed_wiki_fixture(
        settings,
        fixture_name="misconception-chain-rule.after.md",
        target_relative_path="wiki/misconceptions/class-calculus-1-2026-spring-a/chain-rule-product-rule.md",
    )
    seed_wiki_fixture(
        settings,
        fixture_name="operations-refund-policy.seed.md",
        target_relative_path="wiki/operations/class-calculus-1-2026-spring-a/refund-policy.md",
    )


def test_student_wiki_list_returns_academic_pages_in_scope(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_fixture_pack(settings)

    response = client.get(
        "/api/v1/wiki/pages",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-student-wiki-list",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 3
    assert {item["domain"] for item in payload["data"]} == {
        "concepts",
        "faq",
        "misconceptions",
    }


def test_operator_wiki_list_returns_operations_pages_only(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_fixture_pack(settings)

    response = client.get(
        "/api/v1/wiki/pages",
        headers=build_headers(
            role="operator",
            actor_id="ops-academic-office",
            request_id="req-operator-wiki-list",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 1
    assert payload["data"][0]["page_id"] == "page-operations-refund-policy"
    assert payload["data"][0]["domain"] == "operations"


def test_validator_review_domain_can_list_academic_and_operations_pages(
    tmp_path: Path,
) -> None:
    client, settings = build_client(tmp_path)
    seed_fixture_pack(settings)

    response = client.get(
        "/api/v1/wiki/pages",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-validator-wiki-list",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 4
    assert {item["domain"] for item in payload["data"]} == {
        "concepts",
        "faq",
        "misconceptions",
        "operations",
    }


def test_instructor_wiki_list_matches_academic_visibility(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_fixture_pack(settings)

    response = client.get(
        "/api/v1/wiki/pages",
        headers=build_headers(
            role="instructor",
            actor_id="ins-calculus-team",
            request_id="req-instructor-wiki-list",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 3
    assert {item["domain"] for item in payload["data"]} == {
        "concepts",
        "faq",
        "misconceptions",
    }


def test_system_review_domain_can_list_academic_and_operations_pages(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_fixture_pack(settings)

    response = client.get(
        "/api/v1/wiki/pages",
        headers=build_headers(
            role="system",
            actor_id="system-wiki-auditor",
            request_id="req-system-wiki-list",
            domain="review",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 4
    assert {item["domain"] for item in payload["data"]} == {
        "concepts",
        "faq",
        "misconceptions",
        "operations",
    }


def test_wiki_list_without_query_uses_metadata_only_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import knowloop_api.services.wiki as wiki_service

    client, settings = build_client(tmp_path)
    seed_fixture_pack(settings)
    full_page_loads = {"count": 0}
    original_load_wiki_page = wiki_service._load_wiki_page

    def counting_load_wiki_page(path):  # noqa: ANN001
        full_page_loads["count"] += 1
        return original_load_wiki_page(path)

    monkeypatch.setattr(wiki_service, "_load_wiki_page", counting_load_wiki_page)

    response = client.get(
        "/api/v1/wiki/pages?limit=2&offset=1",
        headers=build_headers(
            role="validator",
            actor_id="val-course-admin",
            request_id="req-wiki-list-metadata-only",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 4
    assert len(payload["data"]) == 2
    assert full_page_loads["count"] == 0


@pytest.mark.smoke
def test_wiki_detail_returns_page_body_for_visible_page(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_fixture_pack(settings)

    response = client.get(
        "/api/v1/wiki/pages/page-faq-homework-submission",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-student-wiki-detail",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["page_id"] == "page-faq-homework-submission"
    assert payload["domain"] == "faq"
    assert "Homework 01 is due Friday" in payload["body_markdown"]


def test_wiki_detail_rejects_forbidden_page_scope(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_fixture_pack(settings)

    response = client.get(
        "/api/v1/wiki/pages/page-faq-homework-submission",
        headers=build_headers(
            role="operator",
            actor_id="ops-academic-office",
            request_id="req-operator-forbidden-wiki-detail",
        ),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_scope"


def test_wiki_detail_rejects_cross_class_scope(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_fixture_pack(settings)
    seed_wiki_fixture(
        settings,
        fixture_name="concepts-chain-rule.seed.md",
        target_relative_path="wiki/concepts/class-calculus-1-2026-spring-b/chain-rule-section-b.md",
        replacements={
            "page-concepts-chain-rule": "page-concepts-chain-rule-section-b",
            "class-calculus-1-2026-spring-a": "class-calculus-1-2026-spring-b",
        },
    )

    response = client.get(
        "/api/v1/wiki/pages/page-concepts-chain-rule-section-b",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-student-wiki-cross-class",
        ),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_wiki_detail_resolves_duplicate_page_id_within_request_scope(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_fixture_pack(settings)
    seed_wiki_fixture(
        settings,
        fixture_name="faq-homework-submission.after.md",
        target_relative_path="wiki/faq/class-calculus-1-2026-spring-b/homework-submission.md",
        replacements={
            "class-calculus-1-2026-spring-a": "class-calculus-1-2026-spring-b",
            "Homework 01 is due Friday, April 10 at 11:59 PM KST.": (
                "Section B uses the Monday deadline window."
            ),
        },
    )

    response = client.get(
        "/api/v1/wiki/pages/page-faq-homework-submission",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            class_id="class-calculus-1-2026-spring-b",
            request_id="req-student-wiki-duplicate-page-id-scope",
        ),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["page_id"] == "page-faq-homework-submission"
    assert payload["class_scope"] == "class-calculus-1-2026-spring-b"
    assert "Section B uses the Monday deadline window." in payload["body_markdown"]


def test_wiki_list_ignores_noncanonical_page_paths(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_fixture_pack(settings)
    seed_wiki_fixture(
        settings,
        fixture_name="faq-homework-submission.after.md",
        target_relative_path="wiki/faq/homework-submission-noncanonical.md",
    )

    response = client.get(
        "/api/v1/wiki/pages",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-student-wiki-ignore-noncanonical",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 3
    assert [item["page_id"] for item in payload["data"]].count("page-faq-homework-submission") == 1


def test_wiki_list_skips_malformed_page_frontmatter(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_fixture_pack(settings)
    malformed_path = (
        settings.data_root
        / "wiki"
        / "faq"
        / "class-calculus-1-2026-spring-a"
        / "malformed-homework-page.md"
    )
    malformed_path.parent.mkdir(parents=True, exist_ok=True)
    malformed_path.write_text(
        """---
page_id: page-concepts-homework-submission
domain: faq
title: Broken Homework Page
course_id: course-calculus-1
class_scope: class-calculus-1-2026-spring-a
updated_at: 2026-04-08T11:00:00Z
source_refs: []
candidate_refs: []
summary: This page has a mismatched page_id/domain contract.
---

# Broken Homework Page

This malformed page should be ignored by wiki readers.
""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/v1/wiki/pages",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-student-wiki-ignore-malformed",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 3
    assert all(item["page_id"] != "page-concepts-homework-submission" for item in payload["data"])


def test_wiki_list_skips_unreadable_page_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import knowloop_api.services.wiki as wiki_service

    client, settings = build_client(tmp_path)
    seed_fixture_pack(settings)
    unreadable_path = (
        settings.data_root
        / "wiki"
        / "faq"
        / "class-calculus-1-2026-spring-a"
        / "homework-submission.md"
    )
    original_load = wiki_service._load_wiki_page_metadata

    def flaky_load(path: Path):  # noqa: ANN202
        if path.resolve() == unreadable_path.resolve():
            raise PermissionError("forced wiki read failure")
        return original_load(path)

    monkeypatch.setattr(wiki_service, "_load_wiki_page_metadata", flaky_load)

    response = client.get(
        "/api/v1/wiki/pages",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-student-wiki-ignore-unreadable",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 2
    assert all(item["page_id"] != "page-faq-homework-submission" for item in payload["data"])


def test_wiki_list_applies_limit_and_offset(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_fixture_pack(settings)

    response = client.get(
        "/api/v1/wiki/pages?limit=1&offset=1",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-student-wiki-pagination",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 3
    assert payload["meta"]["limit"] == 1
    assert payload["meta"]["offset"] == 1
    assert len(payload["data"]) == 1


def test_wiki_list_search_ranks_matching_page(tmp_path: Path) -> None:
    client, settings = build_client(tmp_path)
    seed_fixture_pack(settings)

    response = client.get(
        "/api/v1/wiki/pages?q=chain%20rule",
        headers=build_headers(
            role="student",
            actor_id="stu-kim-minji",
            request_id="req-student-wiki-search",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["query"] == "chain rule"
    assert payload["data"][0]["page_id"] == "page-concepts-chain-rule"


def test_internal_wiki_search_respects_operator_visibility_without_explicit_domain(
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    seed_fixture_pack(settings)

    matches = search_wiki_pages(
        settings,
        role=ActorRole.OPERATOR,
        course_id="course-calculus-1",
        class_id="class-calculus-1-2026-spring-a",
        requested_domain=None,
        message="refund policy",
        limit=5,
    )

    assert [match.page.page_id for match in matches] == ["page-operations-refund-policy"]
