# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks top_apps.py (grouping processes into apps)
#   read next → tests/test_system_monitor_storage.py
from typing import Any

import psutil
import pytest

from app.tools.system_monitor.top_apps import (
    AppTotals,
    ProcessSample,
    TopAppsReader,
    find_app_bundle_path,
    group_process_samples_by_app,
    pick_top_apps,
)
from tests.conftest import CHROME, CHROME_HELPER


# LEARN: fakes shaped like psutil's objects, only the parts top_apps.py uses
#   → the test controls exactly what "the system" reports
class FakeMemoryInfo:
    def __init__(self, rss: int) -> None:
        self.rss = rss


class FakeProcess:
    def __init__(
        self, pid: int, name: str, error: type[Exception] | None = None
    ) -> None:
        self.info: dict[str, Any] = {"pid": pid, "name": name, "exe": None}
        self._error = error

    # LEARN: __enter__ / __exit__ → the object works in a with-block
    #   (the real code does: with process.oneshot(): …)
    #   "FakeProcess" in quotes → the class isn't finished yet, so its name
    #   is written as text (industry term: "forward reference")
    def oneshot(self) -> "FakeProcess":
        return self

    def __enter__(self) -> "FakeProcess":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cpu_percent(self, interval: float | None = None) -> float:
        if self._error:
            # e.g. psutil.AccessDenied(3) → like a process we may not read
            raise self._error(self.info["pid"])

        return 12.0

    def memory_info(self) -> FakeMemoryInfo:
        return FakeMemoryInfo(rss=1024)


# test helper: group, then index by app name → apps["Google Chrome"]
def group_by_name(samples: list[ProcessSample]) -> dict[str, AppTotals]:
    return {app.name: app for app in group_process_samples_by_app(samples, cpu_count=8)}


class TestSystemMonitorTopAppsFindAppBundlePath:
    def test_system_monitor_top_apps_find_app_bundle_path_outermost_app(self) -> None:
        assert find_app_bundle_path(CHROME_HELPER) == "/Applications/Google Chrome.app"
        assert find_app_bundle_path(CHROME) == "/Applications/Google Chrome.app"

    def test_system_monitor_top_apps_find_app_bundle_path_outside_apps(self) -> None:
        assert find_app_bundle_path("/usr/bin/python3") is None
        assert find_app_bundle_path(None) is None


class TestSystemMonitorTopAppsGroupProcessSamplesByApp:
    def test_system_monitor_top_apps_group_merges_helpers_into_app(
        self, fake_process_samples: list[ProcessSample]
    ) -> None:
        chrome = group_by_name(fake_process_samples)["Google Chrome"]

        assert chrome.memory_bytes == 2000
        # 80% + 40% of one core each, shared across 8 cores
        assert chrome.cpu_percent == pytest.approx(15.0)
        assert chrome.bundle_path == "/Applications/Google Chrome.app"

    def test_system_monitor_top_apps_group_keeps_processes_by_name(
        self, fake_process_samples: list[ProcessSample]
    ) -> None:
        apps = group_by_name(fake_process_samples)

        assert apps["python3.14"].bundle_path is None
        assert apps["kernel_task"].key == "process:kernel_task"


class TestSystemMonitorTopAppsPickTopApps:
    def test_system_monitor_top_apps_pick_top_apps_sorts_and_limits(self) -> None:
        apps = [
            AppTotals(
                key="a", name="A", bundle_path=None, cpu_percent=5.0, memory_bytes=300
            ),
            AppTotals(
                key="b", name="B", bundle_path=None, cpu_percent=20.0, memory_bytes=100
            ),
            AppTotals(
                key="c", name="C", bundle_path=None, cpu_percent=10.0, memory_bytes=200
            ),
        ]

        by_cpu = pick_top_apps(apps=apps, limit=2, rank_by="cpu")
        by_memory = pick_top_apps(apps=apps, limit=2, rank_by="memory")

        assert [app.key for app in by_cpu] == ["b", "c"]
        assert [app.key for app in by_memory] == ["a", "c"]


class TestSystemMonitorTopAppsReadProcessSamples:
    def test_system_monitor_top_apps_read_process_samples_skips_unreadable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        processes = [
            FakeProcess(pid=1, name="Finder"),
            FakeProcess(pid=2, name="gone", error=psutil.NoSuchProcess),
            FakeProcess(pid=3, name="WindowServer", error=psutil.AccessDenied),
        ]
        # LEARN: monkeypatch.setattr(module, "name", new) → swap a function for
        #   this test only; here psutil.process_iter returns our fakes
        #   industry term: "mocking" / "patching"
        monkeypatch.setattr(psutil, "process_iter", lambda attrs: processes)

        samples = TopAppsReader().read_process_samples()

        assert [sample.name for sample in samples] == ["Finder"]
        assert samples[0].memory_bytes == 1024
