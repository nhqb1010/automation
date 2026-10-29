# LEARN: YOU ARE HERE
#   main.py (window size) + bridge (sidebar, last tool) + preferences.py
#   ▶ THIS FILE reads / writes state.json ▶ remembered at the next start
#   read next → app/tools/__init__.py
"""
Everything the app remembers between launches, kept in one JSON file.

LEARN: no database on purpose
  a handful of values → a small JSON file is enough
  pydantic checks the data on the way in and out

  state.json
  ├── window       size and position
  ├── ui           sidebar collapsed, last open tool
  └── preferences  one section per tool (refresh interval, …)

LEARN: JSON = a text format for data: {"key": value, "list": [1, 2]}
  ≈ a Python dict written as text
"""

import json
import logging
import os

# LEARN: tempfile = make temporary files safely (unique names, right place)
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# LEARN: ValidationError = the error pydantic raises when data doesn't fit
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# How much of a saved window must still be on a screen to reuse its position.
MIN_VISIBLE_WINDOW_PIXELS = 100


class WindowState(BaseModel):
    """LEARN: window size + position (x, y = top-left corner, in points)."""

    width: int
    height: int
    x: int
    y: int


class UiState(BaseModel):
    """LEARN: small UI choices the shell remembers."""

    sidebar_collapsed: bool = False
    last_tool: str | None = None


class AppState(BaseModel):
    """
    LEARN: the whole state.json, as one model

    preferences: dict[str, dict[str, Any]]
      = tool id → that tool's saved settings (checked later by preferences.py)
    """

    window: WindowState | None = None
    ui: UiState = UiState()
    preferences: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True)
class ScreenArea:
    """A screen rectangle with y measured down from the top of the main screen."""

    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class WindowGeometry:
    """LEARN: where to open the window; x / y None → let macOS center it."""

    width: int
    height: int
    x: int | None
    y: int | None


# LEARN: [M: BaseModel] = a "type variable"
#   "M is some kind of BaseModel; whatever class you pass in, you get that
#   same class back" → build_model_leniently(UiState, …) gives a UiState
#   industry term: "generics"
def build_model_leniently[M: BaseModel](model_class: type[M], raw: Any) -> M:
    """
    LEARN: build a model, dropping only the fields that fail the check

    called by → StateStore (ui state) and preferences.py (tool settings)
    gives back → the model with every valid field kept, the rest at default

    hand-edited "refresh_interval_seconds": 7 (not allowed)
      → only that field resets to its default; the rest of the file survives
    """
    # LEARN: isinstance(x, dict) → True if x is a dict
    #   anything else (broken file, a list, …) → plain defaults
    if not isinstance(raw, dict):
        return model_class()

    valid: dict[str, Any] = {}
    # .model_fields → the model's field names
    for name in model_class.model_fields:
        if name not in raw:
            continue

        # try the fields kept so far + this one; failure → skip just this one
        # LEARN: {**valid, name: raw[name]} = copy of valid plus one more key
        try:
            model_class.model_validate({**valid, name: raw[name]})
        except ValidationError:
            logger.warning(
                f"Ignoring invalid saved value {model_class.__name__}.{name}"
            )
            continue

        valid[name] = raw[name]

    # model_validate(dict) → build the model from a dict, checking it
    return model_class.model_validate(valid)


def is_window_visible_on_screens(
    window: WindowState, screens: list[ScreenArea]
) -> bool:
    """
    LEARN: is at least 100 × 100 of the saved window on some screen?

    called by → choose_window_geometry, once at startup

    overlap of two ranges = min(right edges) − max(left edges)
      window:   |-------|
      screen:       |---------|
      overlap:      |---|
    """
    for screen in screens:
        overlap_width = min(window.x + window.width, screen.x + screen.width) - max(
            window.x, screen.x
        )
        overlap_height = min(window.y + window.height, screen.y + screen.height) - max(
            window.y, screen.y
        )
        if (
            overlap_width >= MIN_VISIBLE_WINDOW_PIXELS
            and overlap_height >= MIN_VISIBLE_WINDOW_PIXELS
        ):
            return True

    return False


def choose_window_geometry(
    saved: WindowState | None,
    screens: list[ScreenArea],
    default_size: tuple[int, int],
    min_size: tuple[int, int],
) -> WindowGeometry:
    """
    LEARN: where and how big the window opens

    called by → main.py, once at startup
    gives back → WindowGeometry

      nothing saved, or saved spot is off-screen (monitor unplugged)
        → default size, centered
      saved spot still visible
        → reopen exactly there (never smaller than the minimum)
    """
    default_width, default_height = default_size
    min_width, min_height = min_size
    if saved is None or not is_window_visible_on_screens(saved, screens):
        return WindowGeometry(
            width=default_width, height=default_height, x=None, y=None
        )

    return WindowGeometry(
        width=max(saved.width, min_width),
        height=max(saved.height, min_height),
        x=saved.x,
        y=saved.y,
    )


class StateStore:
    """
    LEARN: loads and saves state.json

    made by → main.py, once at startup
    used by → main.py (window), bridge.py (ui), preferences.py (settings)

    the state lives in memory (self._state); every change is also written
    to the file right away
    lock → the page's calls run on different threads; one change at a time
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._state = self._load_app_state()

    def read_app_state(self) -> AppState:
        with self._lock:
            # deep=True → a full copy; changing it can't touch our original
            return self._state.model_copy(deep=True)

    def save_window_state(self, window: WindowState) -> None:
        with self._lock:
            self._state.window = window
            self._write_state_file()

    def update_ui_state(self, changes: dict[str, Any]) -> UiState:
        with self._lock:
            # LEARN: {**a, **b} = merge two dicts; b's values win
            #   {"sidebar_collapsed": False, "last_tool": "x"}
            #   + {"last_tool": "y"} → {"sidebar_collapsed": False, "last_tool": "y"}
            merged = {**self._state.ui.model_dump(), **changes}
            self._state.ui = build_model_leniently(UiState, merged)
            self._write_state_file()
            return self._state.ui.model_copy()

    def read_tool_preferences_raw(self, tool_id: str) -> dict[str, Any]:
        # "raw" = not checked yet; preferences.py checks it
        with self._lock:
            # dict(…) → a copy, so the caller can't change ours by accident
            return dict(self._state.preferences.get(tool_id, {}))

    def save_tool_preferences_raw(self, tool_id: str, values: dict[str, Any]) -> None:
        with self._lock:
            self._state.preferences[tool_id] = values
            self._write_state_file()

    def _load_app_state(self) -> AppState:
        # first run → no file yet → all defaults
        if not self._path.exists():
            return AppState()

        try:
            # json.loads(text) → Python dicts / lists from JSON text
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            # unreadable (broken JSON) → keep a copy aside, start fresh
            self._set_aside_unreadable_state_file(error)
            return AppState()

        if not isinstance(raw, dict):
            self._set_aside_unreadable_state_file(ValueError("not a JSON object"))
            return AppState()

        # each section is checked on its own → one bad part doesn't wipe the rest
        try:
            window = (
                WindowState.model_validate(raw["window"]) if raw.get("window") else None
            )
        except ValidationError:
            logger.warning("Ignoring invalid saved window state")
            window = None

        preferences = raw.get("preferences")
        return AppState(
            window=window,
            ui=build_model_leniently(UiState, raw.get("ui")),
            # keep only tool sections that are dicts; anything else is dropped
            preferences={
                tool_id: values
                for tool_id, values in (
                    preferences.items() if isinstance(preferences, dict) else []
                )
                if isinstance(values, dict)
            },
        )

    def _set_aside_unreadable_state_file(self, error: Exception) -> None:
        # state.json → state.json.bad (kept for a look later, never lost)
        backup = self._path.with_suffix(".json.bad")
        logger.warning(f"State file unreadable, using defaults {error=} {backup=}")
        try:
            self._path.replace(backup)
        except OSError as rename_error:
            logger.warning(f"Could not set aside the state file {rename_error=}")

    def _write_state_file(self) -> None:
        # LEARN: "atomic write" (industry term)
        #   1. write everything to a temporary file next to state.json
        #   2. swap it in with ONE rename (os.replace)
        #   crash during step 1 → the old state.json is still whole ✓
        #   writing state.json directly → a crash could leave half a file ✗
        payload = self._state.model_dump_json(indent=2)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # "w" → open for writing text
        # delete=False → keep the temp file after closing (we rename it)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self._path.parent,
            prefix=".state-",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_file.write(payload)
            temp_path = Path(temp_file.name)

        os.replace(temp_path, self._path)
