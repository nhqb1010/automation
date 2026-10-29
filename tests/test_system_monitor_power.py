# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks power.py with a fake battery entry
#   (no real ioreg call, works the same on a Mac with no battery)
#   read next → tests/test_system_monitor_top_apps.py
import subprocess
from typing import Any

import pytest

from app.tools.system_monitor import power
from app.tools.system_monitor.power import (
    PowerReader,
    build_power_stats,
    parse_battery_registry,
    to_signed_64_bit,
)


def unplug(raw: dict[str, Any], amperage: int) -> dict[str, Any]:
    # the same battery, on battery power, with the given current
    # {**raw, …} = a copy of raw with these keys changed
    return {
        **raw,
        "ExternalConnected": False,
        "IsCharging": False,
        "InstantAmperage": amperage,
        "PowerTelemetryData": {"SystemPowerIn": 0},
    }


class TestSystemMonitorPowerParseBatteryRegistry:
    def test_system_monitor_power_parse_battery_registry_charging(
        self, fake_battery_registry: dict[str, Any]
    ) -> None:
        reading = parse_battery_registry(fake_battery_registry)

        assert reading.percent == 69
        assert reading.charging
        assert reading.charger_watts == 65
        assert reading.power_in_milliwatts == 57487
        assert reading.time_remaining_minutes == 58

    def test_system_monitor_power_parse_battery_registry_unplugged(
        self, fake_battery_registry: dict[str, Any]
    ) -> None:
        reading = parse_battery_registry(unplug(fake_battery_registry, amperage=-1500))

        assert not reading.plugged_in
        assert reading.charger_watts is None
        assert reading.power_in_milliwatts is None

    def test_system_monitor_power_parse_battery_registry_negative_as_unsigned(
        self, fake_battery_registry: dict[str, Any]
    ) -> None:
        # -1500 mA sent as a huge positive 64-bit number
        raw = unplug(fake_battery_registry, amperage=2**64 - 1500)

        assert parse_battery_registry(raw).amperage_milliamps == -1500

    def test_system_monitor_power_parse_battery_registry_estimating_time(
        self, fake_battery_registry: dict[str, Any]
    ) -> None:
        raw = {**fake_battery_registry, "TimeRemaining": 65535}

        assert parse_battery_registry(raw).time_remaining_minutes is None


class TestSystemMonitorPowerToSigned64Bit:
    def test_system_monitor_power_to_signed_64_bit(self) -> None:
        assert to_signed_64_bit(3910) == 3910
        assert to_signed_64_bit(2**64 - 1) == -1


class TestSystemMonitorPowerBuildPowerStats:
    def test_system_monitor_power_build_power_stats_charging_watts(
        self, fake_battery_registry: dict[str, Any]
    ) -> None:
        stats = build_power_stats(
            reading=parse_battery_registry(fake_battery_registry), history=[]
        )

        # 12.506 V × 3.910 A ≈ 48.9 W into the battery
        assert stats.battery_watts == 48.9
        assert stats.power_in_watts == 57.5
        # 57.487 W in − 48.898 W to the battery ≈ 8.6 W for the Mac itself
        assert stats.mac_watts == 8.6
        assert stats.health_percent == 87.7
        assert stats.temperature_celsius == pytest.approx(30.64)

    def test_system_monitor_power_build_power_stats_on_battery(
        self, fake_battery_registry: dict[str, Any]
    ) -> None:
        raw = {**unplug(fake_battery_registry, amperage=-1500), "Voltage": 12000}

        stats = build_power_stats(reading=parse_battery_registry(raw), history=[])

        assert stats.battery_watts == -18.0
        assert stats.mac_watts == 18.0
        assert stats.power_in_watts is None


class TestSystemMonitorPowerReader:
    def test_system_monitor_power_reader_no_battery_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(power, "read_battery_registry", lambda: None)

        stats = PowerReader().read_power_stats()

        assert not stats.available
        assert stats.reason == "this Mac has no battery"

    def test_system_monitor_power_reader_ioreg_failure_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail_battery_read() -> None:
            raise subprocess.TimeoutExpired(cmd="ioreg", timeout=2)

        monkeypatch.setattr(power, "read_battery_registry", fail_battery_read)

        stats = PowerReader().read_power_stats()

        assert not stats.available
        assert "battery read failed" in (stats.reason or "")

    def test_system_monitor_power_reader_keeps_mac_watts_history(
        self, monkeypatch: pytest.MonkeyPatch, fake_battery_registry: dict[str, Any]
    ) -> None:
        monkeypatch.setattr(
            power, "read_battery_registry", lambda: fake_battery_registry
        )
        reader = PowerReader()

        reader.read_power_stats()
        stats = reader.read_power_stats()

        assert stats.available
        assert stats.history == [8.6, 8.6]
