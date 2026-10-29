# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks app/paths.py (where each copy keeps its data)
#   read next → tests/test_app_build_info.py
import sys
from pathlib import Path

import pytest

from app.paths import APP_NAME, choose_app_locations, is_installed_app

HOME = Path("/Users/someone")
PROJECT = Path("/Users/someone/code/internal_apps")


class TestAppPathsChooseAppLocations:
    def test_app_paths_choose_app_locations_dev_uses_project_folder(self) -> None:
        locations = choose_app_locations(
            is_installed=False, home=HOME, project_root=PROJECT
        )

        assert locations.data_dir == PROJECT
        assert locations.default_log_dir == PROJECT / "logs"
        assert locations.env_file == PROJECT / ".env"

    def test_app_paths_choose_app_locations_installed_uses_library(self) -> None:
        locations = choose_app_locations(
            is_installed=True, home=HOME, project_root=PROJECT
        )

        assert locations.data_dir == HOME / "Library/Application Support" / APP_NAME
        assert locations.default_log_dir == HOME / "Library/Logs" / APP_NAME
        # the installed app never reads a .env
        assert locations.env_file is None


class TestAppPathsIsInstalledApp:
    def test_app_paths_is_installed_app_false_when_run_from_source(self) -> None:
        assert not is_installed_app()

    def test_app_paths_is_installed_app_true_when_frozen(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # raising=False → allowed to add an attribute that doesn't exist yet
        monkeypatch.setattr(sys, "frozen", True, raising=False)

        assert is_installed_app()
