"""The tool registry: every tool the hub shows, in sidebar order."""

from app.tools.base import Tool
from app.tools.system_monitor import SystemMonitorTool


def build_tool_registry() -> list[Tool]:
    # LEARN: adding a tool = import its class and add it here. Like listing an
    # app in Django's INSTALLED_APPS. Tools only start working when this
    # function creates them, not when the module is imported.
    return [SystemMonitorTool()]
