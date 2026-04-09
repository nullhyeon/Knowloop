import json
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "data" / "fixtures"
SCHEMA_ROOT = REPO_ROOT / "schemas"

EXPECTED_FIXTURE_FILES = [
    "sources/lecture-note-week-03-chain-rule.md",
    "sources/announcement-homework-deadline.md",
    "sources/instructor-note-chain-rule-support.md",
    "sources/operations-refund-policy.md",
    "queries/student-chain-rule-confusion.json",
    "queries/student-homework-deadline-01.json",
    "queries/student-homework-deadline-02.json",
    "queries/student-unresolved-question.json",
    "queries/operator-refund-policy.json",
    "queries/instructor-homework-faq.json",
    "sessions/student-minji-history.json",
    "sessions/student-jiyoon-history.json",
    "sessions/student-doyun-history.json",
    "sessions/operator-academic-office-history.json",
    "candidates/open-misconception-chain-rule.json",
    "candidates/open-faq-homework-deadline.json",
    "candidates/open-unresolved-integral.json",
    "candidates/open-operations-refund.json",
    "candidates/open-misconception-chain-rule-duplicate.json",
    "reviews/approve-homework-faq.json",
    "reviews/merge-chain-rule-duplicate.json",
    "reviews/drop-low-value-candidate.json",
    "reviews/patch-preview-homework-faq.json",
    "wiki/concepts-chain-rule.seed.md",
    "wiki/faq-homework-submission.seed.md",
    "wiki/faq-homework-submission.after.md",
    "wiki/misconception-chain-rule.after.md",
    "wiki/operations-refund-policy.seed.md",
]

REQUIRED_CONTEXT_HEADERS = {
    "X-Knowloop-Role",
    "X-Knowloop-Actor-Id",
    "X-Knowloop-Course-Id",
    "X-Knowloop-Class-Id",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_canonical_fixture_pack_contains_expected_files() -> None:
    missing_files = [
        relative_path
        for relative_path in EXPECTED_FIXTURE_FILES
        if not (FIXTURE_ROOT / relative_path).exists()
    ]

    assert missing_files == []


def test_candidate_fixtures_match_candidate_schema() -> None:
    validator = Draft202012Validator(
        json.loads((SCHEMA_ROOT / "candidate_item.json").read_text(encoding="utf-8"))
    )

    for candidate_file in sorted((FIXTURE_ROOT / "candidates").glob("*.json")):
        candidate = load_json(candidate_file)
        errors = sorted(validator.iter_errors(candidate), key=lambda error: error.path)

        assert errors == [], f"{candidate_file.name} failed schema validation: {errors}"


def test_query_fixtures_define_request_context_and_expected_outputs() -> None:
    required_keys = {
        "fixture_id",
        "description",
        "request_headers",
        "request_body",
        "expected",
    }

    for query_file in sorted((FIXTURE_ROOT / "queries").glob("*.json")):
        payload = load_json(query_file)

        assert required_keys.issubset(payload)
        assert REQUIRED_CONTEXT_HEADERS.issubset(payload["request_headers"])
        assert "message" in payload["request_body"]
        assert "answer_basis" in payload["expected"]
        assert "retrieval_entity_types" in payload["expected"]
        assert "writeback_plan" in payload["expected"]
        assert "learning_note_written" in payload["expected"]


def test_review_fixtures_define_idempotent_mutations() -> None:
    required_keys = {
        "fixture_id",
        "description",
        "request_headers",
        "request_body",
        "expected",
    }

    for review_file in sorted((FIXTURE_ROOT / "reviews").glob("*.json")):
        payload = load_json(review_file)

        assert required_keys.issubset(payload)
        assert REQUIRED_CONTEXT_HEADERS.issubset(payload["request_headers"])
        assert (
            "Idempotency-Key" in payload["request_headers"]
            or review_file.name == "patch-preview-homework-faq.json"
        )


def test_wiki_fixture_pages_include_frontmatter_identity() -> None:
    for wiki_file in sorted((FIXTURE_ROOT / "wiki").glob("*.md")):
        contents = wiki_file.read_text(encoding="utf-8")

        assert contents.startswith("---\n")
        assert "page_id:" in contents
        assert "domain:" in contents
        assert "summary:" in contents


def test_candidate_and_review_fixture_references_are_consistent() -> None:
    session_ids = {
        session["session_id"]
        for session_file in sorted((FIXTURE_ROOT / "sessions").glob("*.json"))
        for session in load_json(session_file)
    }
    candidate_ids = set()
    wiki_page_ids = set()

    for wiki_file in sorted((FIXTURE_ROOT / "wiki").glob("*.md")):
        for line in wiki_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("page_id: "):
                wiki_page_ids.add(line.removeprefix("page_id: ").strip())

    for candidate_file in sorted((FIXTURE_ROOT / "candidates").glob("*.json")):
        candidate = load_json(candidate_file)
        candidate_ids.add(candidate["candidate_id"])

        for session_ref in candidate.get("session_refs", []):
            assert session_ref in session_ids

        related_page_id = candidate.get("related_page_id")
        if related_page_id:
            assert related_page_id in wiki_page_ids

    for review_file in sorted((FIXTURE_ROOT / "reviews").glob("*.json")):
        payload = load_json(review_file)
        assert payload["expected"]["candidate_id"] in candidate_ids

        target_page_id = payload["request_body"].get("target_page_id")
        if target_page_id:
            assert target_page_id in wiki_page_ids
