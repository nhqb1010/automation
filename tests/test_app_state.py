# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks app/state.py (state.json, window placement)
#   read next → tests/test_app_usage.py
import json
from pathlib import Path

from app.state import ScreenArea, StateStore, WindowState, choose_window_geometry

# a 14" MacBook screen; sizes as (width, height)
MAIN_SCREEN = ScreenArea(x=0, y=0, width=1512, height=982)
DEFAULT_SIZE = (1000, 680)
MIN_SIZE = (720, 480)


class TestAppStateStore:
    # LEARN: "round trip" (industry term) = save, load again, get the same back
    #   two separate StateStore objects → it really came from the file
    def test_app_state_store_window_state_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        StateStore(path).save_window_state(
            WindowState(width=900, height=600, x=10, y=20)
        )

        assert StateStore(path).read_app_state().window == WindowState(
            width=900, height=600, x=10, y=20
        )

    def test_app_state_store_unreadable_file_set_aside(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        # broken file → defaults, and the file is moved to state.json.bad
        path.write_text("{ not json")

        state = StateStore(path).read_app_state()

        assert state.window is None
        assert (tmp_path / "state.json.bad").exists()
        assert not path.exists()

    def test_app_state_store_invalid_ui_field_falls_back_alone(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "state.json"
        path.write_text(
            # json.dumps(dict) → JSON text; "maybe" is not a bool → only that
            # one field resets, last_tool survives
            json.dumps(
                {"ui": {"sidebar_collapsed": "maybe", "last_tool": "system_monitor"}}
            )
        )

        ui = StateStore(path).read_app_state().ui

        assert ui.sidebar_collapsed is False
        assert ui.last_tool == "system_monitor"

    def test_app_state_store_ui_update_saved_without_temp_files(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "state.json"
        StateStore(path).update_ui_state({"sidebar_collapsed": True})

        assert json.loads(path.read_text())["ui"]["sidebar_collapsed"] is True
        # glob(pattern) → files matching it; none left → temp file was swapped in
        assert not list(tmp_path.glob(".state-*.tmp"))


class TestAppStateChooseWindowGeometry:
    def test_app_state_choose_window_geometry_reuses_saved_window(self) -> None:
        geometry = choose_window_geometry(
            saved=WindowState(width=1100, height=700, x=100, y=80),
            screens=[MAIN_SCREEN],
            default_size=DEFAULT_SIZE,
            min_size=MIN_SIZE,
        )

        assert (geometry.width, geometry.height, geometry.x, geometry.y) == (
            1100,
            700,
            100,
            80,
        )

    def test_app_state_choose_window_geometry_off_screen_centers_default(self) -> None:
        geometry = choose_window_geometry(
            # x=3000 → right of a 1512-wide screen (monitor unplugged)
            saved=WindowState(width=1000, height=680, x=3000, y=100),
            screens=[MAIN_SCREEN],
            default_size=DEFAULT_SIZE,
            min_size=MIN_SIZE,
        )

        assert (geometry.width, geometry.height, geometry.x, geometry.y) == (
            1000,
            680,
            None,
            None,
        )

    def test_app_state_choose_window_geometry_no_saved_window(self) -> None:
        geometry = choose_window_geometry(
            saved=None,
            screens=[MAIN_SCREEN],
            default_size=DEFAULT_SIZE,
            min_size=MIN_SIZE,
        )

        assert geometry.x is None
        assert geometry.width == 1000

    def test_app_state_choose_window_geometry_respects_minimum(self) -> None:
        geometry = choose_window_geometry(
            saved=WindowState(width=300, height=200, x=10, y=10),
            screens=[MAIN_SCREEN],
            default_size=DEFAULT_SIZE,
            min_size=MIN_SIZE,
        )

        assert (geometry.width, geometry.height) == (720, 480)
