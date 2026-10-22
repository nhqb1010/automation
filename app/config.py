"""Developer settings, read from .env (every key starts with BAO_)."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.paths import ENV_FILE, PROJECT_ROOT


class AppSettings(BaseSettings):
    """
    Values a developer may tweak; users change things on the Settings page instead.

    LEARN: pydantic-settings fills each field from the environment or the .env
    file, then validates it. BAO_LOG_LEVEL=DEBUG in .env sets log_level.
    Similar to Django settings, but typed and checked at startup.
    """

    model_config = SettingsConfigDict(
        env_prefix="BAO_", env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    default_window_width: int = Field(default=1000, ge=400)
    default_window_height: int = Field(default=680, ge=300)
    min_window_width: int = Field(default=720, ge=400)
    min_window_height: int = Field(default=480, ge=300)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_dir: Path = Path("logs")

    def resolve_log_dir(self) -> Path:
        return (
            self.log_dir if self.log_dir.is_absolute() else PROJECT_ROOT / self.log_dir
        )
