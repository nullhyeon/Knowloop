from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = Path(__file__).resolve().parents[5]
DATA_ROOT = REPO_ROOT / "data"


class Settings(BaseSettings):
    app_name: str = "Knowloop API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    data_root: Path = DATA_ROOT
    meta_root: Path | None = None
    sessions_db_path: Path | None = None
    audit_db_path: Path | None = None

    @field_validator("data_root", "meta_root", "sessions_db_path", "audit_db_path", mode="before")
    @classmethod
    def resolve_relative_paths(cls, value: Path | str | None) -> Path | None:
        if value is None:
            return None
        path = Path(value)
        if path.is_absolute():
            return path
        return (API_ROOT / path).resolve()

    @model_validator(mode="after")
    def derive_storage_paths(self) -> "Settings":
        if self.meta_root is None:
            self.meta_root = self.data_root / "meta"
        if self.sessions_db_path is None:
            self.sessions_db_path = self.meta_root / "sessions.db"
        if self.audit_db_path is None:
            self.audit_db_path = self.meta_root / "audit.db"
        return self

    model_config = SettingsConfigDict(
        env_file=API_ROOT / ".env",
        env_prefix="KNOWLOOP_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
