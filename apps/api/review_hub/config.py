from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/review-hub.db"
    code_excerpt_max_lines: int = 50
    code_excerpt_max_bytes: int = 16 * 1024

    model_config = SettingsConfigDict(
        env_prefix="REVIEW_HUB_",
        case_sensitive=False,
    )

    def ensure_data_directory(self) -> None:
        if not self.database_url.startswith("sqlite:///"):
            return
        value = self.database_url.removeprefix("sqlite:///")
        if value == ":memory:":
            return
        Path(value).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_data_directory()
    return settings
