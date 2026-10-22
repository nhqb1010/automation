"""
Everything the app remembers between launches, kept in one JSON file.

LEARN: no database here on purpose. A handful of values fits a small JSON
file; pydantic checks it on the way in and out.

  state.json
  ├── window       size and position
  ├── ui           sidebar collapsed, last open tool
  └── preferences  one section per tool (refresh interval, ...)
"""

import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# How much of a saved window must still be on a screen to reuse its position.
MIN_VISIBLE_WINDOW_PIXELS = 100


class WindowState(BaseModel):
    width: int
    height: int
    x: int
    y: int


class UiState(BaseModel):
    sidebar_collapsed: bool = False
    last_tool: str | None = None


class AppState(BaseModel):
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
    width: int
    height: int
    x: int | None
    y: int | None


def build_model_leniently[M: BaseModel](model_class: type[M], raw: Any) -> M:
    """
    Build a model, dropping only the fields that fail validation.

    LEARN: a hand edited value like refresh interval 7 resets just that one
    field to its default instead of throwing away the whole file.

    Args:
        model_class (type[M]): a model whose fields all have defaults.
        raw (Any): the stored data, possibly invalid.
    Returns:
        M: the model with every valid field kept.
    """
    if not isinstance(raw, dict):
        return model_class()

    valid: dict[str, Any] = {}
    for name in model_class.model_fields:
        if name not in raw:
            continue

        try:
            model_class.model_validate({**valid, name: raw[name]})
        except ValidationError:
            logger.warning(
                f"Ignoring invalid saved value {model_class.__name__}.{name}"
            )
            continue

        valid[name] = raw[name]

    return model_class.model_validate(valid)


def is_window_visible_on_screens(
    window: WindowState, screens: list[ScreenArea]
) -> bool:
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
    Reuse the saved window if it still fits on a screen; else center the default.

    Args:
        saved (WindowState | None): the window as it was when last closed.
        screens (list[ScreenArea]): the screens connected right now.
        default_size (tuple[int, int]): width and height for a fresh window.
        min_size (tuple[int, int]): smallest allowed width and height.
    Returns:
        WindowGeometry: size plus position, or no position to let macOS center it.
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
    """Loads and saves state.json; safe to call from several threads."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._state = self._load_app_state()

    def read_app_state(self) -> AppState:
        with self._lock:
            return self._state.model_copy(deep=True)

    def save_window_state(self, window: WindowState) -> None:
        with self._lock:
            self._state.window = window
            self._write_state_file()

    def update_ui_state(self, changes: dict[str, Any]) -> UiState:
        with self._lock:
            merged = {**self._state.ui.model_dump(), **changes}
            self._state.ui = build_model_leniently(UiState, merged)
            self._write_state_file()
            return self._state.ui.model_copy()

    def read_tool_preferences_raw(self, tool_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._state.preferences.get(tool_id, {}))

    def save_tool_preferences_raw(self, tool_id: str, values: dict[str, Any]) -> None:
        with self._lock:
            self._state.preferences[tool_id] = values
            self._write_state_file()

    def _load_app_state(self) -> AppState:
        if not self._path.exists():
            return AppState()

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            self._set_aside_unreadable_state_file(error)
            return AppState()

        if not isinstance(raw, dict):
            self._set_aside_unreadable_state_file(ValueError("not a JSON object"))
            return AppState()

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
            preferences={
                tool_id: values
                for tool_id, values in (
                    preferences.items() if isinstance(preferences, dict) else []
                )
                if isinstance(values, dict)
            },
        )

    def _set_aside_unreadable_state_file(self, error: Exception) -> None:
        backup = self._path.with_suffix(".json.bad")
        logger.warning(f"State file unreadable, using defaults {error=} {backup=}")
        try:
            self._path.replace(backup)
        except OSError as rename_error:
            logger.warning(f"Could not set aside the state file {rename_error=}")

    def _write_state_file(self) -> None:
        # LEARN: write to a temporary file, then swap it in with one rename.
        # A crash mid-write leaves the old file intact instead of half a file.
        payload = self._state.model_dump_json(indent=2)
        self._path.parent.mkdir(parents=True, exist_ok=True)
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
