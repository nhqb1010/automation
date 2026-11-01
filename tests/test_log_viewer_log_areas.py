# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks log_viewer/log_areas.py: which area (and
#   colour) each log source gets
#   read next → tests/test_daily_commit_daily.py
import pytest

from app.tools.log_viewer.log_areas import (
    AUTO_AREA_COLORS,
    find_log_area,
    pick_auto_area_color,
)
from app.tools.log_viewer.models import LogLine


class TestLogViewerLogAreasFindLogArea:
    # LEARN: parametrize → the same test, once per (source, expected) pair
    @pytest.mark.parametrize(
        ("source", "expected_label"),
        [
            ("app.tools.system_monitor.storage", "Monitor"),
            ("app.tools.system_monitor", "Monitor"),
            ("app.tools.daily_commit.github_client", "Daily Commit"),
            ("app.tools.log_viewer.reader", "Logs"),
            ("ui", "Page"),
            ("app.main", "App"),
            ("app.tools", "App"),
            ("app.tools.base", "App"),
            ("pywebview", "Other"),
            ("", "Other"),
        ],
    )
    def test_log_viewer_log_areas_find_log_area_known_sources(
        self, source: str, expected_label: str
    ) -> None:
        assert find_log_area(source).label == expected_label

    def test_log_viewer_log_areas_find_log_area_prefix_needs_a_dot(self) -> None:
        # "app.tools.daily_commits" is another tool, not Daily Commit
        assert find_log_area("app.tools.daily_commits").label == "Daily commits"

    def test_log_viewer_log_areas_find_log_area_new_tool_gets_own_area(self) -> None:
        area = find_log_area("app.tools.backup_repos.runner")

        assert area.id == "backup_repos"
        assert area.label == "Backup repos"
        assert area.color in AUTO_AREA_COLORS


class TestLogViewerLogAreasPickAutoAreaColor:
    def test_log_viewer_log_areas_pick_auto_area_color_is_stable(self) -> None:
        assert pick_auto_area_color("backup_repos") == pick_auto_area_color(
            "backup_repos"
        )


class TestLogViewerLogAreasLogLine:
    def test_log_viewer_log_areas_log_line_sends_area_to_page(self) -> None:
        line = LogLine(
            time="2026-11-03 10:00:00",
            level="INFO",
            source="ui",
            message="hello",
            extra_lines=[],
            continues_previous=False,
        )

        dumped = line.model_dump(mode="json")

        assert dumped["area"]["label"] == "Page"
        assert dumped["area"]["color"].startswith("#")
