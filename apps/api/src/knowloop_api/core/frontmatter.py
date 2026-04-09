from __future__ import annotations

import json
from collections.abc import Mapping


def parse_frontmatter_document(contents: str) -> tuple[dict[str, object], str]:
    if not contents.startswith("---"):
        return {}, contents

    lines = contents.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, contents

    try:
        end_index = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration:
        return {}, contents

    metadata = _parse_frontmatter_lines(lines[1:end_index])
    body = "\n".join(lines[end_index + 1 :]).lstrip("\n")
    if contents.endswith("\n") and body and not body.endswith("\n"):
        body += "\n"
    return metadata, body


def build_frontmatter_document(metadata: Mapping[str, object], body: str) -> str:
    lines = ["---"]
    for key, value in metadata.items():
        if value is None:
            continue
        lines.append(f"{key}: {_serialize_value(value)}")
    lines.append("---")
    lines.append("")
    normalized_body = body.rstrip("\n")
    if normalized_body:
        lines.append(normalized_body)
    return "\n".join(lines).rstrip("\n") + "\n"


def _parse_frontmatter_lines(lines: list[str]) -> dict[str, object]:
    parsed: dict[str, object] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        if ":" not in line:
            raise ValueError(f"unsupported frontmatter line: {line}")

        key, raw_value = line.split(":", maxsplit=1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value:
            parsed[key] = _parse_scalar(raw_value)
            index += 1
            continue

        items: list[object] = []
        index += 1
        while index < len(lines):
            item_line = lines[index]
            if item_line.startswith("  - "):
                items.append(_parse_scalar(item_line[4:].strip()))
                index += 1
                continue
            if not item_line.strip():
                index += 1
                continue
            break
        parsed[key] = items
    return parsed


def _parse_scalar(value: str) -> object:
    if value.startswith(("{", "[")) and value.endswith(("}", "]")):
        return json.loads(value)
    if value.startswith(('"', "'")) and value.endswith(('"', "'")) and len(value) >= 2:
        return value[1:-1]
    return value


def _serialize_value(value: object) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)
