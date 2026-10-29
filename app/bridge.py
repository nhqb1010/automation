# LEARN: YOU ARE HERE
#   page JavaScript ▶ THIS FILE (the only door into Python)
#   ▶ tools / preferences.py / state.py ▶ answer goes back to the page as JSON
#   read next → app/ui/index.html
"""
The one object the page can talk to.

LEARN: pywebview makes every public method of this object callable from
JavaScript as window.pywebview.api.method_name(...), returning a Promise.
Each call runs on its own Python thread, and the return value travels back as
JSON. It works like a Django view with no HTTP and no URL routing:

  page ── api.call("system_monitor", "get_live_stats", {}) ──▶ AppBridge.call
                                                                 │ allow list
                                                                 ▼
  page ◀──────────────── JSON ◀──────────────── SystemMonitorTool.get_live_stats

Anything that must not be callable from the page starts with an underscore:
pywebview skips those.

LEARN: Promise (JavaScript) = "the answer will come later"
  the page doesn't freeze while Python works; see shell.js for how it waits
"""

import logging
from typing import Any

from app.build_info import BuildInfo, format_build_label
from app.preferences import PreferencesService
from app.state import StateStore
from app.tools.base import Tool, UnknownToolActionError

logger = logging.getLogger(__name__)
# a separate logger named "ui" → page errors are easy to spot in app.log
client_logger = logging.getLogger("ui")


class AppBridge:
    """
    LEARN: every method the page may call

    made by → main.py, passed to the window as js_api
    called by → shell.js, settings.js, and each tool's view.js

    all answers are plain dicts / lists → pywebview turns them into JSON
    model_dump(mode="json") = pydantic model → JSON-safe dict
    """

    def __init__(
        self,
        tools: list[Tool],
        preferences: PreferencesService,
        store: StateStore,
        build_info: BuildInfo,
    ) -> None:
        # tool id → tool, for quick lookup
        self._tools = {tool.info.id: tool for tool in tools}
        self._preferences = preferences
        self._store = store
        self._build_info = build_info

    def list_tools(self) -> list[dict[str, str]]:
        """called by → shell.js at startup ▶ builds the sidebar."""
        return [
            {
                "id": tool.info.id,
                "name": tool.info.name,
                "icon": tool.info.icon,
                "description": tool.info.description,
            }
            for tool in self._tools.values()
        ]

    def get_ui_state(self) -> dict[str, Any]:
        """called by → shell.js at startup ▶ sidebar open/closed, last tool."""
        return self._store.read_app_state().ui.model_dump(mode="json")

    def update_ui_state(self, changes: dict[str, Any]) -> dict[str, Any]:
        """called by → shell.js (sidebar toggled, tool opened) ▶ saved."""
        return self._store.update_ui_state(changes).model_dump(mode="json")

    def load_tool_view(self, tool_id: str) -> dict[str, str]:
        """called by → shell.js, first open of a tool ▶ its html / css / js."""
        return self._find_tool(tool_id).read_tool_view().model_dump()

    def call(
        self, tool_id: str, action: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        LEARN: run one tool action (the main door for tool pages)

        called by → a tool's view.js, e.g. every refresh
        gives back → the action's result as a dict ▶ JSON ▶ the page

        any error is logged here, then raised again ("raise" alone)
          → the page's Promise fails and the page shows the problem
        """
        tool = self._find_tool(tool_id)
        try:
            # "params or {}" → None becomes an empty dict
            result = tool.run_tool_action(action=action, params=params or {})
        except UnknownToolActionError:
            logger.warning(f"Rejected unknown action {tool_id=} {action=}")
            raise
        except Exception:
            # logger.exception → also logs the full traceback
            logger.exception(f"Tool action failed {tool_id=} {action=}")
            raise

        return result.model_dump(mode="json")

    def get_tool_preferences(self, tool_id: str) -> dict[str, Any]:
        """called by → a tool's view.js ▶ its current settings."""
        return self._preferences.read_tool_preferences(tool_id).model_dump(mode="json")

    def update_tool_preference(
        self, tool_id: str, field: str, value: Any
    ) -> dict[str, Any]:
        """called by → settings.js, a button click ▶ checked + saved."""
        updated = self._preferences.update_tool_preference(
            tool_id=tool_id, field=field, value=value
        )
        return updated.model_dump(mode="json")

    def reset_tool_preferences(self, tool_id: str) -> dict[str, Any]:
        """called by → settings.js, the Reset button ▶ defaults saved."""
        return self._preferences.reset_tool_preferences(tool_id).model_dump(mode="json")

    def get_settings_sections(self) -> list[dict[str, Any]]:
        """called by → settings.js, Settings page opens ▶ rows to draw."""
        return [
            section.model_dump(mode="json")
            for section in self._preferences.describe_settings_sections()
        ]

    def get_app_info(self) -> dict[str, Any]:
        """called by → settings.js ▶ the version line under the settings."""
        return {
            "label": format_build_label(self._build_info),
            "is_dev": self._build_info.is_dev,
        }

    def log_client_error(self, message: str, source: str, line: int) -> None:
        """
        LEARN: errors in the page's JavaScript would otherwise vanish

        called by → shell.js, on any page error
        written to → logs/app.log, same file as Python errors
        """
        client_logger.error(f"{source}:{line} {message}")

    def _find_tool(self, tool_id: str) -> Tool:
        # starts with _ → pywebview hides it from the page
        tool = self._tools.get(tool_id)
        if tool is None:
            logger.warning(f"Rejected unknown tool {tool_id=}")
            raise UnknownToolActionError(f"Unknown tool {tool_id!r}")

        return tool
