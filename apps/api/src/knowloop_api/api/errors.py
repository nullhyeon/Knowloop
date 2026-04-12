from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ApiError(Exception):
    status_code: int
    code: str
    message: str
    request_id: str
    details: dict[str, Any] = field(default_factory=dict)
    retry_after_seconds: int | None = None

    def to_payload(self, *, request_id: str | None = None) -> dict[str, Any]:
        return {
            "request_id": request_id or self.request_id,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
        }


def success_response(
    request_id: str,
    data: Any,
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "data": data,
        "meta": meta or {},
    }
