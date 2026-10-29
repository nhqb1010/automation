# LEARN: YOU ARE HERE
#   make test ▶ pytest loads THIS FILE first ▶ every test file gets these fakes
#   read next → tests/test_app_config.py
"""
Shared fakes for every test.

LEARN: fixtures defined here are available to all test files by name, with no
import. Fake system data keeps results the same on any machine.

LEARN: how pytest works (see tests/README.md for the full picture)
  test file  = test_*.py
  test class = Test… (a group of tests, no __init__ needed)
  test       = a method named test_…
  assert x   → the test fails if x is false

LEARN: fixture = a ready-made input a test asks for BY NAME
  def test_x(self, fake_clock: FakeClock) → pytest calls fake_clock() below
  and passes the result in; each test gets a fresh one
  @pytest.fixture = the decorator that marks a function as a fixture
  industry term: "test fixture" / "dependency injection"

LEARN: fake (industry term: "test double")
  a stand-in for the real thing (clock, sensors, drives)
  → same result on every Mac, no waiting, no real hardware
"""

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from app.state import StateStore
from app.tools.base import Tool, ToolInfo
from app.tools.system_monitor.storage import MountedVolume
from app.tools.system_monitor.temperature import SensorReading
from app.tools.system_monitor.top_apps import ProcessSample

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_HELPER = (
    "/Applications/Google Chrome.app/Contents/Frameworks/"
    "Google Chrome Framework.framework/Versions/131/Helpers/"
    "Google Chrome Helper (Renderer).app/Contents/MacOS/"
    "Google Chrome Helper (Renderer)"
)


class FakeClock:
    """
    A clock tests can move forward by hand.

    LEARN: replaces time.monotonic in recent_values.py
      fake_clock.advance(10) → "10 seconds pass" instantly
    """

    def __init__(self) -> None:
        self.now = 1000.0

    # LEARN: __call__ → the object can be called like a function
    #   fake_clock() → 1000.0 (same as how time.monotonic() is called)
    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# LEARN: a tiny pretend tool, so bridge / preferences tests don't need the
#   real System Monitor (which reads the real Mac)
class EchoResult(BaseModel):
    text: str


class DummySettings(BaseModel):
    speed: int = 1


class DummyTool(Tool):
    info = ToolInfo(id="dummy", name="Dummy", icon="activity", description="test tool")
    settings_model = DummySettings
    actions = frozenset({"echo_text"})
    ui_dir = Path(__file__).parent

    def echo_text(self, text: str) -> EchoResult:
        return EchoResult(text=text)

    # public, but NOT in actions → the bridge must refuse it (allow list test)
    def secret_helper(self) -> EchoResult:
        return EchoResult(text="should never be reachable")


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


# LEARN: tmp_path = a built-in pytest fixture: a fresh empty folder per test,
#   deleted later → tests never touch the real state.json
@pytest.fixture
def state_store(tmp_path: Path) -> StateStore:
    return StateStore(tmp_path / "state.json")


@pytest.fixture
def dummy_tool() -> DummyTool:
    return DummyTool()


# Chrome main + Chrome helper → should group into ONE "Google Chrome" app
# kernel_task has no exe path → grouped by its name
@pytest.fixture
def fake_process_samples() -> list[ProcessSample]:
    return [
        ProcessSample(
            pid=1, name="Google Chrome", exe=CHROME, cpu_percent=80.0, memory_bytes=500
        ),
        ProcessSample(
            pid=2,
            name="Google Chrome Helper (Renderer)",
            exe=CHROME_HELPER,
            cpu_percent=40.0,
            memory_bytes=1500,
        ),
        ProcessSample(
            pid=3,
            name="python3.14",
            exe="/usr/bin/python3",
            cpu_percent=16.0,
            memory_bytes=300,
        ),
        ProcessSample(
            pid=4, name="kernel_task", exe=None, cpu_percent=8.0, memory_bytes=100
        ),
    ]


# Tp = CPU P-core, Te = CPU E-core, Tg = GPU
# -50 and 250 → impossible values the reader must ignore
@pytest.fixture
def fake_smc_readings() -> list[SensorReading]:
    return [
        SensorReading(name="Tp01", celsius=50.0),
        SensorReading(name="Tp05", celsius=60.0),
        SensorReading(name="Te01", celsius=40.0),
        SensorReading(name="Tg05", celsius=45.0),
        SensorReading(name="Tg0D", celsius=47.0),
        SensorReading(name="Tp09", celsius=-50.0),
        SensorReading(name="Tp0D", celsius=250.0),
    ]


# fallback sensors: only "PMU tdie" ones count as the chip temperature
@pytest.fixture
def fake_hid_readings() -> list[SensorReading]:
    return [
        SensorReading(name="PMU tdie1", celsius=36.0),
        SensorReading(name="PMU tdie2", celsius=38.0),
        SensorReading(name="NAND CH0 temp", celsius=31.0),
        SensorReading(name="gas gauge battery", celsius=30.0),
    ]


# a messy real-world list: system volumes, a duplicate T7, Time Machine
# snapshots, hidden volumes → storage.py must keep only real drives
# a MacBook charging from a 65 W charger (values copied from a real ioreg read)
@pytest.fixture
def fake_battery_registry() -> dict[str, Any]:
    return {
        "ExternalConnected": True,
        "IsCharging": True,
        "FullyCharged": False,
        "CurrentCapacity": 69,
        "TimeRemaining": 58,
        "Voltage": 12506,
        "Amperage": 3910,
        "InstantAmperage": 3910,
        "DesignCapacity": 6075,
        "AppleRawMaxCapacity": 5329,
        "CycleCount": 149,
        "Temperature": 3064,
        "AdapterDetails": {"Watts": 65, "Description": "pd charger"},
        "PowerTelemetryData": {"SystemPowerIn": 57487},
    }


@pytest.fixture
def fake_mounted_volumes() -> list[MountedVolume]:
    return [
        MountedVolume(mountpoint="/", fstype="apfs"),
        MountedVolume(mountpoint="/System/Volumes/VM", fstype="apfs"),
        MountedVolume(mountpoint="/System/Volumes/Data", fstype="apfs"),
        MountedVolume(mountpoint="/dev", fstype="devfs"),
        MountedVolume(mountpoint="/Volumes/T7", fstype="exfat"),
        MountedVolume(mountpoint="/Volumes/NAS", fstype="smbfs"),
        MountedVolume(mountpoint="/Volumes/Installer", fstype="hfs"),
        MountedVolume(mountpoint="/Volumes/T7", fstype="exfat"),
        MountedVolume(
            mountpoint=(
                "/Volumes/com.apple.TimeMachine.localsnapshots/Backups.backupdb/"
                "Mac/2026-10-22-120000/Data"
            ),
            fstype="apfs",
        ),
        MountedVolume(mountpoint="/Volumes/.timemachine", fstype="apfs"),
    ]
