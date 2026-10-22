"""System Monitor: CPU, RAM, temperature, top apps and storage."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.tools.base import Tool, ToolInfo
from app.tools.system_monitor.cpu_memory import CpuMemoryReader
from app.tools.system_monitor.models import LiveStats, StorageStats, TopApps
from app.tools.system_monitor.storage import StorageReader
from app.tools.system_monitor.temperature import TemperatureMonitor
from app.tools.system_monitor.top_apps import TopAppsReader


class SystemMonitorSettings(BaseModel):
    # LEARN: Literal limits a field to fixed choices. The Settings page turns
    # each set of choices into a row of buttons automatically.
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
    cpu_top_apps_open: bool = Field(default=False, json_schema_extra={"hidden": True})
    memory_top_apps_open: bool = Field(
        default=False, json_schema_extra={"hidden": True}
    )


class SystemMonitorTool(Tool):
    info = ToolInfo(
        id="system_monitor",
        name="System Monitor",
        icon="activity",
        description="CPU, RAM, temperature, top apps and storage.",
    )
    settings_model = SystemMonitorSettings
    actions = frozenset({"get_live_stats", "get_top_apps", "get_storage"})
    ui_dir = Path(__file__).parent / "ui"

    def __init__(self) -> None:
        self._cpu_memory = CpuMemoryReader()
        self._temperature = TemperatureMonitor()
        self._top_apps = TopAppsReader()
        self._storage = StorageReader()

    def get_live_stats(self) -> LiveStats:
        return LiveStats(
            cpu=self._cpu_memory.read_cpu_stats(),
            memory=self._cpu_memory.read_memory_stats(),
            temperature=self._temperature.read_temperature_stats(),
        )

    def get_top_apps(self, limit: int) -> TopApps:
        return self._top_apps.read_top_apps(limit)

    def get_storage(self) -> StorageStats:
        return self._storage.read_storage_stats()
