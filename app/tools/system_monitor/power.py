# LEARN: YOU ARE HERE
#   system_monitor/__init__.py, every live refresh ▶ THIS FILE asks macOS
#   about the battery and charger ▶ PowerStats ▶ JSON ▶ the Power card
#   read next → app/tools/system_monitor/top_apps.py
"""
Battery and charger: charge level, charging or not, and the watts flowing.

LEARN: where the numbers come from

  ioreg = macOS's tool for listing hardware and its live values
  "ioreg -a -rn AppleSmartBattery" → the battery's entry, as a plist
    (no password needed, same as System Information → Power)

  charger ──▶ Mac ──▶ battery
    │          │        └ Voltage (mV) × Amperage (mA) = battery watts
    │          └ what the Mac uses = power in − battery watts
    └ AdapterDetails.Watts      = the charger's rating (e.g. 65 W)
      PowerTelemetryData.SystemPowerIn = watts coming in right now (mW)

  units: mV = millivolts, mA = milliamps, mW = milliwatts (÷ 1000)
  watts = volts × amps
"""

import logging
import plistlib
import subprocess
from dataclasses import dataclass
from typing import Any

from app.tools.system_monitor.models import PowerStats
from app.tools.system_monitor.recent_values import RecentValues

logger = logging.getLogger(__name__)

IOREG_PATH = "/usr/sbin/ioreg"
IOREG_TIMEOUT_SECONDS = 2
# macOS's "still estimating" value for the time remaining
TIME_REMAINING_UNKNOWN = 65535
# LEARN: two's complement (industry term)
#   ioreg can hand a NEGATIVE current over as a huge positive number
#   (the same 64 bits read as "unsigned")
#   anything ≥ 2**63 really means value − 2**64, e.g. 2**64 − 500 → −500
SIGNED_64_BIT_LIMIT = 2**63
UNSIGNED_64_BIT_RANGE = 2**64


@dataclass(frozen=True)
class BatteryReading:
    """
    LEARN: the battery values we use, in plain units, from ioreg's raw dict

    made by → parse_battery_registry
    used by → build_power_stats
    """

    percent: int
    plugged_in: bool
    charging: bool
    fully_charged: bool
    time_remaining_minutes: int | None
    voltage_millivolts: int
    amperage_milliamps: int
    charger_watts: int | None
    power_in_milliwatts: int | None
    design_capacity: int | None
    max_capacity: int | None
    cycle_count: int | None
    # ioreg gives hundredths of a degree: 3064 → 30.64 °C
    temperature_centi_celsius: int | None


def read_battery_registry() -> dict[str, Any] | None:
    """
    LEARN: run ioreg and give back the battery's raw entry

    called by → PowerReader.read_power_stats, every live refresh
    gives back → a dict of ioreg values, or None when there is no battery
    errors (ioreg missing, timeout, bad output) are raised to the caller

    -a → output as a plist; -r -n AppleSmartBattery → only that entry
    (subprocess.run options explained in cpu_memory.py)
    """
    result = subprocess.run(
        [IOREG_PATH, "-a", "-r", "-n", "AppleSmartBattery"],
        capture_output=True,
        check=True,
        timeout=IOREG_TIMEOUT_SECONDS,
    )
    # a Mac with no battery → empty output → no entry
    if not result.stdout.strip():
        return None

    entries = plistlib.loads(result.stdout)
    # the answer is a list of matching entries; a Mac has one battery
    return entries[0] if entries else None


def to_signed_64_bit(value: int) -> int:
    """LEARN: fix a negative number that arrived as a huge positive one."""
    return value - UNSIGNED_64_BIT_RANGE if value >= SIGNED_64_BIT_LIMIT else value


def read_optional_int(raw: dict[str, Any], key: str) -> int | None:
    # LEARN: isinstance(True, int) is True in Python (bool is a kind of int)
    #   → booleans are ruled out on purpose
    value = raw.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value

    return None


def parse_battery_registry(raw: dict[str, Any]) -> BatteryReading:
    """
    LEARN: pick and clean the values we need from ioreg's battery entry

    called by → PowerReader.read_power_stats
    gives back → BatteryReading
    missing values → None (older Macs lack the telemetry part)
    """
    # "or {}" → a missing section becomes an empty dict, so .get still works
    adapter = raw.get("AdapterDetails") or {}
    telemetry = raw.get("PowerTelemetryData") or {}
    time_remaining = read_optional_int(raw, "TimeRemaining")
    plugged_in = bool(raw.get("ExternalConnected"))
    power_in = read_optional_int(telemetry, "SystemPowerIn")
    return BatteryReading(
        percent=read_optional_int(raw, "CurrentCapacity") or 0,
        plugged_in=plugged_in,
        charging=bool(raw.get("IsCharging")),
        fully_charged=bool(raw.get("FullyCharged")),
        time_remaining_minutes=(
            None if time_remaining in (None, TIME_REMAINING_UNKNOWN) else time_remaining
        ),
        voltage_millivolts=read_optional_int(raw, "Voltage") or 0,
        # InstantAmperage = right now; Amperage = a short average (fallback)
        amperage_milliamps=to_signed_64_bit(
            read_optional_int(raw, "InstantAmperage")
            or read_optional_int(raw, "Amperage")
            or 0
        ),
        charger_watts=read_optional_int(adapter, "Watts") if plugged_in else None,
        # 0 while unplugged → treated as "no reading"
        power_in_milliwatts=power_in if plugged_in and power_in else None,
        design_capacity=read_optional_int(raw, "DesignCapacity"),
        # AppleRawMaxCapacity = what the battery holds today (mAh);
        # MaxCapacity is a percent on Apple Silicon, so it's only a fallback
        max_capacity=read_optional_int(raw, "AppleRawMaxCapacity"),
        cycle_count=read_optional_int(raw, "CycleCount"),
        temperature_centi_celsius=read_optional_int(raw, "Temperature"),
    )


def calculate_battery_watts(reading: BatteryReading) -> float:
    """
    LEARN: watts into (+) or out of (−) the battery

    mV × mA = microwatts → ÷ 1 000 000 = watts
      12 506 mV × 3 910 mA = 48 898 460 µW ≈ 48.9 W (charging)
    """
    return reading.voltage_millivolts * reading.amperage_milliamps / 1_000_000


def calculate_mac_watts(reading: BatteryReading, battery_watts: float) -> float | None:
    """
    LEARN: what the Mac itself is using

      on battery → everything comes from the battery → −battery watts
      plugged in → charger power minus what goes into the battery
      plugged in, no charger reading → unknown (None)
    max(0, …) → small timing differences can't make it negative
    """
    if not reading.plugged_in:
        return max(0.0, -battery_watts)
    if reading.power_in_milliwatts is None:
        return None

    return max(0.0, reading.power_in_milliwatts / 1000 - battery_watts)


def build_power_stats(reading: BatteryReading, history: list[float]) -> PowerStats:
    """
    LEARN: turn a reading into what the Power card shows

    called by → PowerReader.read_power_stats
    gives back → PowerStats ▶ JSON ▶ the page
    round(x, 1) → one decimal, e.g. 48.898 → 48.9
    """
    battery_watts = calculate_battery_watts(reading)
    mac_watts = calculate_mac_watts(reading=reading, battery_watts=battery_watts)
    health = (
        reading.max_capacity / reading.design_capacity * 100
        if reading.max_capacity and reading.design_capacity
        else None
    )
    return PowerStats(
        available=True,
        percent=reading.percent,
        plugged_in=reading.plugged_in,
        charging=reading.charging,
        fully_charged=reading.fully_charged,
        minutes_remaining=reading.time_remaining_minutes,
        charger_watts=reading.charger_watts,
        power_in_watts=(
            round(reading.power_in_milliwatts / 1000, 1)
            if reading.power_in_milliwatts is not None
            else None
        ),
        battery_watts=round(battery_watts, 1),
        mac_watts=round(mac_watts, 1) if mac_watts is not None else None,
        # min(100, …) → a new battery can report slightly over its design
        health_percent=round(min(100.0, health), 1) if health is not None else None,
        cycle_count=reading.cycle_count,
        temperature_celsius=(
            reading.temperature_centi_celsius / 100
            if reading.temperature_centi_celsius is not None
            else None
        ),
        history=history,
    )


class PowerReader:
    """
    LEARN: reads battery + charger once per refresh, remembers recent watts

    made by → SystemMonitorTool, once at startup
    called by → SystemMonitorTool.get_live_stats, every refresh
    """

    def __init__(self) -> None:
        # the last 60 s of "Mac watts" → the card's sparkline
        self._recent_mac_watts = RecentValues()
        # each problem is logged once, not every 2 seconds
        self._logged_reasons: set[str] = set()

    def read_power_stats(self) -> PowerStats:
        """
        gives back → PowerStats; available False (with a reason) when there
        is no battery or ioreg failed, never an error
        """
        try:
            raw = read_battery_registry()
        except (
            OSError,
            subprocess.SubprocessError,
            plistlib.InvalidFileException,
        ) as error:
            return self._build_unavailable_power_stats(f"battery read failed: {error}")

        if raw is None:
            return self._build_unavailable_power_stats("this Mac has no battery")

        reading = parse_battery_registry(raw)
        stats = build_power_stats(reading=reading, history=[])
        if stats.mac_watts is not None:
            self._recent_mac_watts.add_sample(stats.mac_watts)

        # model_copy(update=…) → a copy with some fields changed
        return stats.model_copy(update={"history": self._recent_mac_watts.values()})

    def _build_unavailable_power_stats(self, reason: str) -> PowerStats:
        if reason not in self._logged_reasons:
            logger.warning(f"Power reading unavailable {reason=}")
            self._logged_reasons.add(reason)

        return PowerStats(available=False, reason=reason)
