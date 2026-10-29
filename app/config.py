# LEARN: YOU ARE HERE
#   main.py at startup ▶ THIS FILE reads .env ▶ AppSettings
#   ▶ window size (main.py) + log level / folder (logging_setup.py)
#   read next → app/build_info.py
"""Developer settings, read from .env (every key starts with BAO_)."""

from pathlib import Path
from typing import Literal

from pydantic import Field

# LEARN: pydantic-settings = pydantic models filled from the environment
#   ≈ Django's settings.py, but typed and checked at startup
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.paths import DEFAULT_LOG_DIR, ENV_FILE, PROJECT_ROOT


class AppSettings(BaseSettings):
    """
    LEARN: values a DEVELOPER may tweak, in a .env file

    made by → main.py, once at startup
    users change their settings on the Settings page instead (preferences.py)

    how a value is found, for each field:
      environment variable BAO_<FIELD>  ─┐
      .env file line BAO_<FIELD>=…      ─┼─ first one found wins
      the default written below         ─┘
    then checked: BAO_LOG_LEVEL=LOUD → error at startup ✓

    the installed Mac app reads no .env (env_file=None) → defaults only
    """

    # LEARN: model_config = settings for the model itself
    #   env_prefix="BAO_" → field log_level reads BAO_LOG_LEVEL
    #   extra="ignore" → other keys in .env don't cause an error
    model_config = SettingsConfigDict(
        env_prefix="BAO_", env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    # LEARN: Field(default=1000, ge=400) → default 1000, must be ≥ 400
    #   ge = "greater than or equal"
    default_window_width: int = Field(default=1000, ge=400)
    default_window_height: int = Field(default=680, ge=300)
    min_window_width: int = Field(default=720, ge=400)
    min_window_height: int = Field(default=480, ge=300)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # None → this copy's default (project logs/ in dev, ~/Library/Logs installed)
    log_dir: Path | None = None

    def resolve_log_dir(self) -> Path:
        # not set → default; "logs" (relative) → inside the project folder;
        # "/tmp/x" (absolute) → as given
        if self.log_dir is None:
            return DEFAULT_LOG_DIR
        if self.log_dir.is_absolute():
            return self.log_dir

        return PROJECT_ROOT / self.log_dir
