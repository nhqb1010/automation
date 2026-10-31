# LEARN: YOU ARE HERE
#   Settings page (every 2 s while open) ▶ bridge get_app_usage
#   ▶ THIS FILE measures how much CPU and memory the app itself uses
#   ▶ the "This app's own usage" card ▶ you change a setting, watch it drop
#   read next → app/login_item.py
"""
How much CPU and memory this app uses, so setting changes can be compared.

LEARN: the app is more than one process

  Bao Internal Apps (Python)   reads stats, answers the page   ← always counted
  com.apple.WebKit.WebContent  draws the window's contents     ← counted if found
  com.apple.WebKit.Networking  WebKit's helper                 ← counted if found

  the WebKit helpers are started by macOS, not by us, so they aren't our
  "children"; macOS still records which app they work for ("responsible
  process"), the same link Activity Monitor uses to group them under an app
  that link is read with an undocumented macOS call → if it ever fails, the
  card says it counts the app's own code only

LEARN: CPU % here = share of the WHOLE processor (all cores together),
  the same scale as the Top apps list (Activity Monitor uses one core = 100 %)
"""

import ctypes
import logging
import os
import time
from collections.abc import Callable
from typing import Any, Protocol

import psutil
from pydantic import BaseModel

from app.tools.system_monitor.recent_values import RecentValues

logger = logging.getLogger(__name__)

LIBSYSTEM_PATH = "/usr/lib/libSystem.B.dylib"
WEBKIT_PROCESS_PREFIX = "com.apple.WebKit."
# looking through every process costs CPU itself → only every 30 s
HELPER_SEARCH_INTERVAL_SECONDS = 30.0


class AppUsage(BaseModel):
    """
    LEARN: one reading for the own-usage card

    made by → AppUsageMonitor.read_app_usage
    cpu_percent → right now; cpu_average → over the last 60 s
    includes_display_processes False → only the Python side was measured
    history → the last 60 s of cpu_percent → the card's sparkline
    """

    cpu_percent: float
    cpu_average: float
    memory_bytes: int
    process_count: int
    includes_display_processes: bool
    history: list[float]


class MeasuredProcess(Protocol):
    """
    LEARN: the two things we need from a process (psutil.Process has them)

    Protocol = "anything with these methods fits" (industry term: duck typing)
    → tests can pass a small fake instead of a real process
    """

    def cpu_percent(self, interval: float | None = None) -> float: ...

    # gives back an object with .rss (bytes held in memory)
    def memory_info(self) -> Any: ...


def read_responsible_pid(pid: int) -> int | None:
    """
    LEARN: which app macOS says this process works for

    ctypes → call a C function inside a macOS system library directly
    responsibility_get_pid_responsible_for_pid is undocumented (Activity
    Monitor relies on it) → any failure gives None, never a crash
    """
    try:
        function = ctypes.CDLL(
            LIBSYSTEM_PATH
        ).responsibility_get_pid_responsible_for_pid
    except OSError, AttributeError:
        return None

    function.argtypes = [ctypes.c_int]
    function.restype = ctypes.c_int
    responsible = function(pid)
    return responsible if responsible > 0 else None


def find_display_helper_pids(
    owner_pid: int, find_responsible_pid: Callable[[int], int | None]
) -> list[int]:
    """
    LEARN: the WebKit helper processes working for owner_pid

    called by → AppUsageMonitor, at most every 30 s
    gives back → their process ids (empty if none found)
    """
    helper_pids = []
    for process in psutil.process_iter(["pid", "name"]):
        name = process.info["name"] or ""
        if not name.startswith(WEBKIT_PROCESS_PREFIX):
            continue

        if find_responsible_pid(process.info["pid"]) == owner_pid:
            helper_pids.append(process.info["pid"])

    return helper_pids


class AppUsageMonitor:
    """
    LEARN: measures the app's own processes, keeps the last 60 s

    made by → main.py, once at startup
    called by → bridge.get_app_usage, every 2 s while Settings is open

    psutil's cpu_percent(None) = CPU used since the LAST call on the same
    object → the process objects are kept between calls (first call = 0)
    """

    def __init__(
        self,
        own_pid: int | None = None,
        find_helper_pids: Callable[[int], list[int]] | None = None,
        open_process: Callable[[int], MeasuredProcess] = psutil.Process,
        cpu_count: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._own_pid = own_pid if own_pid is not None else os.getpid()
        # LEARN: "x if x is not None else default" → a default that's
        #   worked out at run time (a function default is fixed at import)
        self._find_helper_pids = find_helper_pids or (
            lambda pid: find_display_helper_pids(
                owner_pid=pid, find_responsible_pid=read_responsible_pid
            )
        )
        self._open_process = open_process
        self._cpu_count = cpu_count or psutil.cpu_count() or 1
        self._clock = clock
        self._processes: dict[int, MeasuredProcess] = {}
        self._helper_pids: list[int] = []
        self._helpers_searched_at: float | None = None
        self._recent_cpu = RecentValues(clock=clock)

    def read_app_usage(self) -> AppUsage:
        """
        gives back → AppUsage for the app's own process + its WebKit helpers
        a process that has quit since last time is simply dropped
        """
        self._refresh_helper_pids()
        total_cpu = 0.0
        total_memory = 0
        measured = 0
        for pid in [self._own_pid, *self._helper_pids]:
            try:
                process = self._processes.get(pid) or self._open_process(pid)
                self._processes[pid] = process
                total_cpu += process.cpu_percent(None)
                # rss = the memory the process really holds right now
                total_memory += process.memory_info().rss
            except psutil.Error:
                self._processes.pop(pid, None)
                continue

            measured += 1

        cpu_share = total_cpu / self._cpu_count
        self._recent_cpu.add_sample(cpu_share)
        history = self._recent_cpu.values()
        return AppUsage(
            cpu_percent=round(cpu_share, 2),
            cpu_average=round(sum(history) / len(history), 2),
            memory_bytes=total_memory,
            process_count=measured,
            includes_display_processes=measured > 1,
            history=history,
        )

    def _refresh_helper_pids(self) -> None:
        now = self._clock()
        searched_at = self._helpers_searched_at
        if (
            searched_at is not None
            and now - searched_at < HELPER_SEARCH_INTERVAL_SECONDS
        ):
            return

        self._helpers_searched_at = now
        self._helper_pids = self._find_helper_pids(self._own_pid)
        # forget processes that are no longer ours
        keep = {self._own_pid, *self._helper_pids}
        self._processes = {
            pid: process for pid, process in self._processes.items() if pid in keep
        }
