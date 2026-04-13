from __future__ import annotations

import json
from functools import lru_cache

from pydantic import BaseModel

from knowloop_api.core.config import Settings
from knowloop_api.core.contracts import ActorRole, RequestDomain


class ContextProfile(BaseModel):
    profile_id: str
    label: str
    role: ActorRole
    actor_id: str
    course_id: str
    class_id: str
    domain: RequestDomain
    landing_surface: str
    description: str | None = None


class ContextProfileNotFoundError(KeyError):
    """Raised when a profile id cannot be resolved from the profile registry."""


def list_context_profiles(settings: Settings) -> list[ContextProfile]:
    return list(_load_context_profiles(settings.context_profiles_path))


def get_context_profile(settings: Settings, profile_id: str) -> ContextProfile:
    for profile in _load_context_profiles(settings.context_profiles_path):
        if profile.profile_id == profile_id:
            return profile
    raise ContextProfileNotFoundError(profile_id)


@lru_cache(maxsize=8)
def _load_context_profiles(path) -> tuple[ContextProfile, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(ContextProfile.model_validate(item) for item in payload)
