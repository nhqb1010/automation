# LEARN: YOU ARE HERE
#   tool registry makes this tool at startup (with the log file's path)
#   page ▶ bridge.call("log_viewer", "read_new_log_lines") ▶ THIS FILE
#   ▶ reader.py ▶ LogChunk ▶ JSON ▶ page
#   read next → app/tools/log_viewer/models.py
"""
Logs: the app's own log file, live, inside the app.

LEARN: the same plug-in shape as System Monitor (see app/tools/base.py)
  info / settings_model / actions / ui_dir → sidebar, Settings, page

  page asks                 this file          does the work
  read_new_log_lines ──▶ LogViewerTool ──▶ reader.read_new_log_lines
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.tools.base import Tool, ToolInfo
from app.tools.log_viewer.models import LogChunk, LogCursor
from app.tools.log_viewer.reader import read_new_log_lines

# never send more than this many lines in one answer, whatever the page asks
MAX_LINES_PER_ANSWER = 5000


class LogViewerSettings(BaseModel):
    """
    LEARN: this tool's user settings (the "Logs" section on Settings)

    read by → app/preferences.py, which draws them as rows of buttons
    """

    refresh_interval_seconds: Literal[1, 2, 5] = Field(
        default=1,
        title="Refresh interval",
        description="How often new log lines are fetched.",
        json_schema_extra={"unit": "s"},
    )
    max_lines: Literal[500, 1000, 2000, 5000] = Field(
        default=2000,
        title="Lines kept",
        description="Older lines drop off the page past this number.",
    )


class LogViewerTool(Tool):
    """
    LEARN: the Logs tool, as the hub sees it

    made by → app/tools/__init__.py (the registry), once at startup
    called by → app/bridge.py, when the page asks for read_new_log_lines
    """

    info = ToolInfo(
        id="log_viewer",
        name="Logs",
        icon="scroll-text",
        description="The app's own log, live.",
    )
    settings_model = LogViewerSettings
    actions = frozenset({"read_new_log_lines"})
    ui_dir = Path(__file__).parent / "ui"

    def __init__(self, log_file: Path) -> None:
        # log_file comes from logging_setup.py, via main.py and the registry
        self._log_file = log_file

    def read_new_log_lines(
        self, cursor: dict[str, Any] | None = None, max_lines: int = 2000
    ) -> LogChunk:
        """
        LEARN: new lines since the page's bookmark

        called by → bridge.call, every poll (default every second)
        cursor → the bookmark from the last answer, as plain JSON (a dict)
          None → the page just opened → the last part of the file
        gives back → LogChunk ▶ JSON ▶ the page
        """
        # model_validate(dict) → check the bookmark the page sent back
        parsed_cursor = LogCursor.model_validate(cursor) if cursor else None
        # keep the number in a safe range: at least 1, at most 5000
        line_limit = max(1, min(max_lines, MAX_LINES_PER_ANSWER))
        return read_new_log_lines(
            log_file=self._log_file, cursor=parsed_cursor, max_lines=line_limit
        )
