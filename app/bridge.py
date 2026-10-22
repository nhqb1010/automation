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
"""

import logging
from typing import Any

from app.preferences import PreferencesService
from app.state import StateStore
from app.tools.base import Tool, UnknownToolActionError

logger = logging.getLogger(__name__)
client_logger = logging.getLogger("ui")


class AppBridge:
    def __init__(
        self, tools: list[Tool], preferences: PreferencesService, store: StateStore
    ) -> None:
        self._tools = {tool.info.id: tool for tool in tools}
        self._preferences = preferences
        self._store = store

    def list_tools(self) -> list[dict[str, str]]:
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
        return self._store.read_app_state().ui.model_dump(mode="json")

    def update_ui_state(self, changes: dict[str, Any]) -> dict[str, Any]:
        return self._store.update_ui_state(changes).model_dump(mode="json")

    def load_tool_view(self, tool_id: str) -> dict[str, str]:
        return self._find_tool(tool_id).read_tool_view().model_dump()

    def call(
        self, tool_id: str, action: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        tool = self._find_tool(tool_id)
        try:
            result = tool.run_tool_action(action=action, params=params or {})
        except UnknownToolActionError:
            logger.warning(f"Rejected unknown action {tool_id=} {action=}")
            raise
        except Exception:
            logger.exception(f"Tool action failed {tool_id=} {action=}")
            raise

        return result.model_dump(mode="json")

    def get_tool_preferences(self, tool_id: str) -> dict[str, Any]:
        return self._preferences.read_tool_preferences(tool_id).model_dump(mode="json")

    def update_tool_preference(
        self, tool_id: str, field: str, value: Any
    ) -> dict[str, Any]:
        updated = self._preferences.update_tool_preference(
            tool_id=tool_id, field=field, value=value
        )
        return updated.model_dump(mode="json")

    def reset_tool_preferences(self, tool_id: str) -> dict[str, Any]:
        return self._preferences.reset_tool_preferences(tool_id).model_dump(mode="json")

    def get_settings_sections(self) -> list[dict[str, Any]]:
        return [
            section.model_dump(mode="json")
            for section in self._preferences.describe_settings_sections()
        ]

    def log_client_error(self, message: str, source: str, line: int) -> None:
        # LEARN: errors in the page's JavaScript would otherwise vanish. The
        # shell forwards them here so they land in the same log file.
        client_logger.error(f"{source}:{line} {message}")

    def _find_tool(self, tool_id: str) -> Tool:
        tool = self._tools.get(tool_id)
        if tool is None:
            logger.warning(f"Rejected unknown tool {tool_id=}")
            raise UnknownToolActionError(f"Unknown tool {tool_id!r}")

        return tool
