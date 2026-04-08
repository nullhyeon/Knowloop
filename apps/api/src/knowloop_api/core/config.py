from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = Path(__file__).resolve().parents[5]
DATA_ROOT = REPO_ROOT / "data"


class Settings(BaseSettings):
    app_name: str = "Knowloop API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    data_root: Path = DATA_ROOT
    meta_root: Path = DATA_ROOT / "meta"
    sessions_db_path: Path = DATA_ROOT / "meta" / "sessions.db"
    audit_db_path: Path = DATA_ROOT / "meta" / "audit.db"

    @field_validator("data_root", "meta_root", "sessions_db_path", "audit_db_path", mode="before")
    @classmethod
    def resolve_relative_paths(cls, value: Path | str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return (API_ROOT / path).resolve()

    model_config = SettingsConfigDict(
        env_file=API_ROOT / ".env",
        env_prefix="KNOWLOOP_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
