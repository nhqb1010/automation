"""
Shared fakes for every test.

LEARN: fixtures defined here are available to all test files by name, with no
import. Fake system data keeps results the same on any machine.
"""

from pathlib import Path

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
    """A clock tests can move forward by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


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

    def secret_helper(self) -> EchoResult:
        return EchoResult(text="should never be reachable")


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def state_store(tmp_path: Path) -> StateStore:
    return StateStore(tmp_path / "state.json")


@pytest.fixture
def dummy_tool() -> DummyTool:
    return DummyTool()


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


@pytest.fixture
def fake_hid_readings() -> list[SensorReading]:
    return [
        SensorReading(name="PMU tdie1", celsius=36.0),
        SensorReading(name="PMU tdie2", celsius=38.0),
        SensorReading(name="NAND CH0 temp", celsius=31.0),
        SensorReading(name="gas gauge battery", celsius=30.0),
    ]


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
