# LEARN: YOU ARE HERE
#   tool registry makes this tool at startup
#   page ▶ bridge.call("system_monitor", action) ▶ THIS FILE picks the reader
#   ▶ reader result ▶ JSON ▶ page
#   read next → app/tools/system_monitor/models.py
"""
System Monitor: CPU, RAM, temperature, power, top apps and storage.

LEARN: __init__.py = the file that runs when you import the folder itself
  "from app.tools.system_monitor import SystemMonitorTool" reads THIS file

LEARN: this file is the tool's "front desk"; the readers do the real work

  page asks          this file          does the work
  get_live_stats ──▶ CpuMemoryReader + TemperatureMonitor + PowerReader
  get_top_apps   ──▶ TopAppsReader
  get_storage    ──▶ StorageReader
  get_mac_info   ──▶ MacInfoReader (once per visit)
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.tools.base import Tool, ToolInfo
from app.tools.system_monitor.cpu_memory import CpuMemoryReader
from app.tools.system_monitor.mac_info import MacInfoReader
from app.tools.system_monitor.models import LiveStats, MacInfo, StorageStats, TopApps
from app.tools.system_monitor.power import PowerReader
from app.tools.system_monitor.storage import StorageReader
from app.tools.system_monitor.temperature import TemperatureMonitor
from app.tools.system_monitor.top_apps import TopAppsReader


class SystemMonitorSettings(BaseModel):
    """
    LEARN: this tool's user settings (the "System Monitor" section)

    read by → app/preferences.py, which builds the Settings page from it
    saved in → state.json

    Literal[1, 2, 5, 10] → only these values allowed
      → the Settings page shows them as a row of buttons, automatically

    Field(...) = extra info about a field
      default → value when nothing is saved
      title / description → the text shown on the Settings page
      json_schema_extra → our own extra tags:
        "unit": "s"      → buttons read "1s 2s 5s 10s"
        "hidden": True   → saved, but NOT shown on the Settings page
    """

    refresh_interval_seconds: Literal[1, 2, 5, 10] = Field(
        default=2,
        title="Refresh interval",
        description="How often CPU, RAM and temperature update.",
        json_schema_extra={"unit": "s"},
    )
    top_apps_count: Literal[3, 5, 10] = Field(
        default=5,
        title="Top apps shown",
        description="How many apps each top apps list shows.",
    )
    # remembers whether each Top apps list was left open (hidden setting)
    cpu_top_apps_open: bool = Field(default=False, json_schema_extra={"hidden": True})
    memory_top_apps_open: bool = Field(
        default=False, json_schema_extra={"hidden": True}
    )


# LEARN: class SystemMonitorTool(Tool) = "inherits from Tool"
#   → gets Tool's shared behaviour (run_tool_action, read_tool_view)
#   → only fills in what's specific to this tool
class SystemMonitorTool(Tool):
    """
    LEARN: the System Monitor, as the hub sees it

    made by → app/tools/__init__.py (the registry), once at startup
    called by → app/bridge.py, whenever the page asks for one of "actions"
    """

    # LEARN: these four are CLASS attributes (shared, set once for the class)
    #   the shell reads them to plug the tool in
    info = ToolInfo(
        id="system_monitor",
        name="System Monitor",
        icon="activity",
        description="CPU, RAM, temperature, power, top apps and storage.",
    )
    settings_model = SystemMonitorSettings
    # the ONLY methods the page may call; anything else is refused
    actions = frozenset(
        {"get_live_stats", "get_top_apps", "get_storage", "get_mac_info"}
    )
    # LEARN: Path(__file__) = this file's own location
    #   .parent / "ui" → the ui folder next to it (view.html / .css / .js)
    ui_dir = Path(__file__).parent / "ui"

    def __init__(self) -> None:
        # each reader starts once here and lives as long as the app
        self._cpu_memory = CpuMemoryReader()
        self._temperature = TemperatureMonitor()
        self._power = PowerReader()
        self._mac_info = MacInfoReader()
        self._top_apps = TopAppsReader()
        self._storage = StorageReader()

    def get_live_stats(self) -> LiveStats:
        # called every refresh (default every 2 s)
        #   → CPU + Memory + Temperature + Power
        return LiveStats(
            cpu=self._cpu_memory.read_cpu_stats(),
            memory=self._cpu_memory.read_memory_stats(),
            temperature=self._temperature.read_temperature_stats(),
            power=self._power.read_power_stats(),
        )

    def get_top_apps(self, limit: int) -> TopApps:
        # called every refresh, only while a Top apps list is open
        return self._top_apps.read_top_apps(limit)

    def get_storage(self) -> StorageStats:
        # called every 30 s
        return self._storage.read_storage_stats()

    def get_mac_info(self) -> MacInfo:
        # called once each time the page opens (the values don't change)
        return self._mac_info.read_mac_info()
