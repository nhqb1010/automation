# LEARN: YOU ARE HERE
#   main.py at startup ▶ THIS FILE makes every tool ▶ list of tools
#   ▶ bridge (page calls) + preferences (Settings page) + sidebar
#   read next → app/tools/base.py
"""The tool registry: every tool the hub shows, in sidebar order."""

from pathlib import Path

from app.tools.base import Tool
from app.tools.log_viewer import LogViewerTool
from app.tools.system_monitor import SystemMonitorTool


def build_tool_registry(log_file: Path) -> list[Tool]:
    """
    LEARN: the list of tools the app shows

    called by → main.py, once at startup
    gives back → one object per tool, in sidebar order

    registry (industry term) = one central list of the parts that are plugged in
      adding a tool = import its class + add it to this list
      ≈ listing an app in Django's INSTALLED_APPS

    SystemMonitorTool() → makes the tool → its readers start here
    LogViewerTool(log_file=…) → needs to know which file to show
      log_file = the path logging_setup.py opened (passed in by main.py)
    """
    return [SystemMonitorTool(), LogViewerTool(log_file=log_file)]
