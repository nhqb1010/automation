from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import AppSettings
from app.paths import PROJECT_ROOT


def build_settings_without_env_file() -> AppSettings:
    # ignore any real .env on this machine so results are the same everywhere
    return AppSettings(_env_file=None)


class TestAppConfigDefaults:
    def test_app_config_defaults(self) -> None:
        settings = build_settings_without_env_file()

        assert settings.default_window_width == 1000
        assert settings.log_level == "INFO"
        assert settings.resolve_log_dir() == PROJECT_ROOT / "logs"


class TestAppConfigEnvironment:
    def test_app_config_environment_overrides_with_bao_prefix(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("BAO_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("BAO_LOG_DIR", str(tmp_path))

        settings = build_settings_without_env_file()

        assert settings.log_level == "DEBUG"
        assert settings.resolve_log_dir() == tmp_path

    def test_app_config_environment_invalid_log_level_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BAO_LOG_LEVEL", "LOUD")

        with pytest.raises(ValidationError):
            build_settings_without_env_file()
