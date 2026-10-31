# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks app/app_usage.py (the app's own CPU / memory)
#   with pretend processes → no real measuring, same result on any Mac
#   read next → tests/test_app_login_item.py
from typing import Any

import psutil
import pytest

from app.app_usage import AppUsageMonitor, find_display_helper_pids
from tests.conftest import FakeClock, FakeMeasuredProcess

OWN_PID = 100
HELPER_PIDS = [201, 202]


def build_monitor(
    processes: dict[int, FakeMeasuredProcess],
    helper_pids: list[int],
    fake_clock: FakeClock,
    helper_searches: list[int] | None = None,
) -> AppUsageMonitor:
    # helper_searches (optional) → records each helper search, to count them
    def find_helper_pids(owner_pid: int) -> list[int]:
        if helper_searches is not None:
            helper_searches.append(owner_pid)

        return helper_pids

    return AppUsageMonitor(
        own_pid=OWN_PID,
        find_helper_pids=find_helper_pids,
        open_process=lambda pid: processes[pid],
        cpu_count=4,
        clock=fake_clock,
    )


class TestAppUsageReadAppUsage:
    def test_app_usage_read_app_usage_own_process_only(
        self, fake_clock: FakeClock
    ) -> None:
        processes = {OWN_PID: FakeMeasuredProcess(cpu_percent=8.0, rss=50_000_000)}
        monitor = build_monitor(processes, helper_pids=[], fake_clock=fake_clock)

        usage = monitor.read_app_usage()

        # 8 % of one core, shared across 4 cores → 2 % of the whole CPU
        assert usage.cpu_percent == 2.0
        assert usage.memory_bytes == 50_000_000
        assert usage.process_count == 1
        assert not usage.includes_display_processes

    def test_app_usage_read_app_usage_adds_display_helpers(
        self, fake_clock: FakeClock
    ) -> None:
        processes = {
            OWN_PID: FakeMeasuredProcess(cpu_percent=4.0, rss=50),
            201: FakeMeasuredProcess(cpu_percent=8.0, rss=30),
            202: FakeMeasuredProcess(cpu_percent=0.0, rss=20),
        }
        monitor = build_monitor(processes, HELPER_PIDS, fake_clock=fake_clock)

        usage = monitor.read_app_usage()

        assert usage.cpu_percent == 3.0
        assert usage.memory_bytes == 100
        assert usage.process_count == 3
        assert usage.includes_display_processes

    def test_app_usage_read_app_usage_average_over_history(
        self, fake_clock: FakeClock
    ) -> None:
        own = FakeMeasuredProcess(cpu_percent=4.0, rss=1)
        monitor = build_monitor({OWN_PID: own}, helper_pids=[], fake_clock=fake_clock)
        monitor.read_app_usage()
        fake_clock.advance(2)
        own.reported_cpu = 12.0

        usage = monitor.read_app_usage()

        assert usage.history == [1.0, 3.0]
        assert usage.cpu_average == 2.0

    def test_app_usage_read_app_usage_skips_process_that_quit(
        self, fake_clock: FakeClock
    ) -> None:
        processes = {
            OWN_PID: FakeMeasuredProcess(cpu_percent=4.0, rss=10),
            201: FakeMeasuredProcess(cpu_percent=4.0, rss=10, gone=True),
        }
        monitor = build_monitor(processes, helper_pids=[201], fake_clock=fake_clock)

        usage = monitor.read_app_usage()

        assert usage.process_count == 1
        assert usage.memory_bytes == 10

    def test_app_usage_read_app_usage_searches_helpers_every_30_seconds(
        self, fake_clock: FakeClock
    ) -> None:
        searches: list[int] = []
        processes = {OWN_PID: FakeMeasuredProcess(cpu_percent=0.0, rss=1)}
        monitor = build_monitor(
            processes, helper_pids=[], fake_clock=fake_clock, helper_searches=searches
        )

        monitor.read_app_usage()
        fake_clock.advance(10)
        monitor.read_app_usage()
        fake_clock.advance(25)
        monitor.read_app_usage()

        assert searches == [OWN_PID, OWN_PID]


class FakeListedProcess:
    """LEARN: what psutil.process_iter yields: an object with .info."""

    def __init__(self, pid: int, name: str) -> None:
        self.info: dict[str, Any] = {"pid": pid, "name": name}


class TestAppUsageFindDisplayHelperPids:
    def test_app_usage_find_display_helper_pids_only_ours(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        listed = [
            FakeListedProcess(201, "com.apple.WebKit.WebContent"),
            FakeListedProcess(202, "com.apple.WebKit.Networking"),
            # a WebKit helper working for another app (Mail, Safari, …)
            FakeListedProcess(203, "com.apple.WebKit.WebContent"),
            # ours, but not a WebKit helper
            FakeListedProcess(204, "Python"),
        ]
        monkeypatch.setattr(psutil, "process_iter", lambda attrs: listed)
        responsible = {201: OWN_PID, 202: OWN_PID, 203: 999, 204: OWN_PID}

        pids = find_display_helper_pids(
            owner_pid=OWN_PID, find_responsible_pid=responsible.get
        )

        assert pids == [201, 202]
