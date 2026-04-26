import math
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from knowloop_api.core.input_limits import MAX_API_REQUEST_BODY_BYTES

API_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = Path(__file__).resolve().parents[5]
DATA_ROOT = REPO_ROOT / "data"


class Settings(BaseSettings):
    app_name: str = "Knowloop API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    data_root: Path = DATA_ROOT
    context_trust_mode: Literal["legacy_headers", "signed"] = "legacy_headers"
    demo_context_profiles_enabled: bool | None = None
    trusted_context_secret: SecretStr | None = None
    trusted_context_max_age_seconds: int = 300
    llm_enabled: bool = False
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.4"
    openai_reasoning_effort: Literal["minimal", "low", "medium", "high"] = "low"
    openai_text_verbosity: Literal["low", "medium", "high"] = "medium"
    openai_timeout_seconds: float = 30.0
    openai_max_output_tokens: int = 450
    meta_root: Path | None = None
    sessions_db_path: Path | None = None
    audit_db_path: Path | None = None
    context_profiles_path: Path | None = None
    max_api_request_body_bytes: int = MAX_API_REQUEST_BODY_BYTES

    @field_validator(
        "data_root",
        "meta_root",
        "sessions_db_path",
        "audit_db_path",
        "context_profiles_path",
        mode="before",
    )
    @classmethod
    def resolve_relative_paths(cls, value: Path | str | None) -> Path | None:
        if value is None:
            return None
        path = Path(value)
        if path.is_absolute():
            return path
        return (API_ROOT / path).resolve()

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def normalize_openai_api_key(cls, value: SecretStr | str | None) -> SecretStr | None:
        if value is None:
            return None
        raw_value = value.get_secret_value() if isinstance(value, SecretStr) else str(value)
        normalized = raw_value.strip()
        if not normalized:
            return None
        return SecretStr(normalized)

    @field_validator("openai_model", mode="before")
    @classmethod
    def normalize_openai_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("openai_model must not be blank")
        return normalized

    @field_validator("openai_timeout_seconds")
    @classmethod
    def validate_openai_timeout_seconds(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("openai_timeout_seconds must be finite")
        if value <= 0 or value > 300:
            raise ValueError("openai_timeout_seconds must be between 0 and 300")
        return value

    @field_validator("openai_max_output_tokens")
    @classmethod
    def validate_openai_max_output_tokens(cls, value: int) -> int:
        if value <= 0 or value > 4000:
            raise ValueError("openai_max_output_tokens must be between 1 and 4000")
        return value

    @field_validator("trusted_context_secret", mode="before")
    @classmethod
    def normalize_trusted_context_secret(cls, value: SecretStr | str | None) -> SecretStr | None:
        if value is None:
            return None
        raw_value = value.get_secret_value() if isinstance(value, SecretStr) else str(value)
        normalized = raw_value.strip()
        if not normalized:
            return None
        return SecretStr(normalized)

    @field_validator("trusted_context_max_age_seconds")
    @classmethod
    def validate_trusted_context_max_age_seconds(cls, value: int) -> int:
        if value <= 0 or value > 86_400:
            raise ValueError("trusted_context_max_age_seconds must be between 1 and 86400")
        return value

    @field_validator("max_api_request_body_bytes")
    @classmethod
    def validate_max_api_request_body_bytes(cls, value: int) -> int:
        if value <= 0 or value > MAX_API_REQUEST_BODY_BYTES:
            raise ValueError(
                f"max_api_request_body_bytes must be between 1 and {MAX_API_REQUEST_BODY_BYTES}"
            )
        return value

    @model_validator(mode="after")
    def derive_storage_paths(self) -> "Settings":
        if self.meta_root is None:
            self.meta_root = self.data_root / "meta"
        if self.sessions_db_path is None:
            self.sessions_db_path = self.meta_root / "sessions.db"
        if self.audit_db_path is None:
            self.audit_db_path = self.meta_root / "audit.db"
        if self.context_profiles_path is None:
            self.context_profiles_path = (
                REPO_ROOT / "data" / "fixtures" / "context" / "profiles.json"
            )
        normalized_env = self.app_env.strip().lower()
        if self.demo_context_profiles_enabled is None:
            self.demo_context_profiles_enabled = normalized_env not in {"production", "prod"}
        if normalized_env in {"production", "prod"} and self.context_trust_mode != "signed":
            raise ValueError("context_trust_mode must be signed when app_env=production")
        if normalized_env in {"production", "prod"} and self.demo_context_profiles_enabled:
            raise ValueError("demo_context_profiles_enabled must be false when app_env=production")
        if self.context_trust_mode == "signed" and self.trusted_context_secret is None:
            raise ValueError("trusted_context_secret is required when context_trust_mode=signed")
        if self.context_trust_mode == "signed" and self.trusted_context_secret is not None:
            secret_value = self.trusted_context_secret.get_secret_value()
            if len(secret_value.encode("utf-8")) < 32:
                raise ValueError(
                    "trusted_context_secret must be at least 32 bytes when "
                    "context_trust_mode=signed"
                )
        if self.llm_enabled and not self.openai_api_key:
            raise ValueError("openai_api_key is required when llm_enabled=true")
        return self

    model_config = SettingsConfigDict(
        env_file=API_ROOT / ".env",
        env_prefix="KNOWLOOP_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
