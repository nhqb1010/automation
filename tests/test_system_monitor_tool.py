# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks system_monitor/__init__.py: its settings
#   (defaults the Settings page shows) and which actions the page may call
#   read next → tests/test_system_monitor_top_apps.py
from app.tools.system_monitor import SystemMonitorSettings, SystemMonitorTool
from app.tools.system_monitor.models import LiveStats


class TestSystemMonitorToolSettings:
    def test_system_monitor_tool_settings_defaults(self) -> None:
        settings = SystemMonitorSettings()

        assert settings.refresh_interval_seconds == 2
        assert settings.battery_refresh_seconds == 10
        assert settings.storage_refresh_seconds == 30
        assert settings.slow_down_in_background


class TestSystemMonitorToolActions:
    def test_system_monitor_tool_actions_include_power(self) -> None:
        assert SystemMonitorTool.actions == {
            "get_live_stats",
            "get_power",
            "get_top_apps",
            "get_storage",
            "get_mac_info",
        }

    def test_system_monitor_tool_actions_live_stats_without_power(self) -> None:
        # the battery has its own, slower timer → not part of every refresh
        assert "power" not in LiveStats.model_fields
