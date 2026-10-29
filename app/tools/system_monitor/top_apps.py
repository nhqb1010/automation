# LEARN: YOU ARE HERE
#   page refresh (only while a "Top apps" list is open) ▶ bridge
#   ▶ System Monitor tool ▶ THIS FILE scans every running process
#   ▶ TopApps (two ranked lists) ▶ JSON ▶ the app rows on the page
#   read next → app/tools/system_monitor/app_icons.py
"""Which apps use the most CPU and RAM, helpers grouped under their app."""

import logging
import threading
from dataclasses import dataclass

# LEARN: PurePosixPath = a file path as an object, split into parts
#   "Pure" → only does text work on the path, never touches the disk
from pathlib import PurePosixPath
from typing import Literal

import psutil

from app.tools.system_monitor.app_icons import AppIconCache
from app.tools.system_monitor.models import AppUsage, TopApps
from app.tools.system_monitor.recent_values import RecentValuesPerApp

logger = logging.getLogger(__name__)

APP_BUNDLE_SUFFIX = ".app"
MAX_TOP_APPS = 20

type RankBy = Literal["cpu", "memory"]


@dataclass(frozen=True)
class ProcessSample:
    """
    LEARN: one running program at one moment

    process = one running program; one app can run many (Chrome runs dozens)
    pid = process id, the number macOS gives each running process
    exe = full path of the program file (None when macOS hides it from us)
    """

    pid: int
    name: str
    exe: str | None
    cpu_percent: float
    memory_bytes: int


@dataclass(frozen=True)
class AppTotals:
    """LEARN: one app with all its processes added together."""

    key: str
    name: str
    bundle_path: str | None
    cpu_percent: float
    memory_bytes: int


def find_app_bundle_path(exe: str | None) -> str | None:
    """
    LEARN: find the outermost ".app" folder a program lives in

    called by → group_process_samples_by_app, once per process
    gives back → e.g. "/Applications/Google Chrome.app", or None

    app bundle = a macOS app is really a folder ending in .app
    helpers live INSIDE their app's folder:

      Google Chrome.app/…/Google Chrome Helper (Renderer).app/…
      ↑ outermost .app = the app the user knows → group under it
    """
    if not exe:
        return None

    # .parts → ("/", "Applications", "Google Chrome.app", "Contents", …)
    parts = PurePosixPath(exe).parts
    for index, part in enumerate(parts):
        if part.endswith(APP_BUNDLE_SUFFIX):
            # LEARN: parts[: index + 1] = slice: items 0 up to and incl. index
            #   PurePosixPath(*parts) = join the parts back into one path
            return str(PurePosixPath(*parts[: index + 1]))

    return None


def group_process_samples_by_app(
    samples: list[ProcessSample], cpu_count: int
) -> list[AppTotals]:
    """
    LEARN: add up CPU + RAM per app; programs outside any app keep their name

    called by → TopAppsReader.read_top_apps (and tests, with fake samples)
    gives back → one AppTotals per app or standalone program

    CPU scale: macOS counts per core → one busy core = 100 %, 8 cores = 800 %
      ÷ core count → a share of the WHOLE CPU (0–100 %), like the main ring
    """
    divisor = max(cpu_count, 1)

    # LEARN: dict used as a running total: key → AppTotals so far
    totals: dict[str, AppTotals] = {}
    for sample in samples:
        bundle_path = find_app_bundle_path(sample.exe)
        # not inside an app → its own entry, e.g. "process:python3.14"
        key = bundle_path or f"process:{sample.name}"
        # .stem → last part without its ending: "Google Chrome.app" → "Google Chrome"
        name = PurePosixPath(bundle_path).stem if bundle_path else sample.name
        current = totals.get(key)
        # AppTotals is frozen (read-only) → build a new one with the sums
        totals[key] = AppTotals(
            key=key,
            name=name,
            bundle_path=bundle_path,
            cpu_percent=(current.cpu_percent if current else 0.0)
            + sample.cpu_percent / divisor,
            memory_bytes=(current.memory_bytes if current else 0) + sample.memory_bytes,
        )

    # .values() → just the AppTotals, list() → a plain list of them
    return list(totals.values())


def pick_top_apps(
    apps: list[AppTotals], limit: int, rank_by: RankBy
) -> list[AppTotals]:
    """
    LEARN: sort biggest first, keep the first "limit" apps

    called by → TopAppsReader.read_top_apps, twice (by CPU, by memory)
    """
    # LEARN: match / case = pick a branch by value (like a tidy if / elif)
    #
    # LEARN: sorted(items, key=..., reverse=True)
    #   key = a function that says WHAT to sort by
    #   lambda app: app.cpu_percent = a tiny unnamed function:
    #     def sort_value(app): return app.cpu_percent
    #   reverse=True → biggest first
    match rank_by:
        case "cpu":
            ranked = sorted(apps, key=lambda app: app.cpu_percent, reverse=True)
        case "memory":
            ranked = sorted(apps, key=lambda app: app.memory_bytes, reverse=True)

    # [:limit] → only the first "limit" items
    return ranked[:limit]


class TopAppsReader:
    """
    LEARN: builds the two "Top apps" lists

    made by → the System Monitor tool, once at startup
    called by → the tool's get_top_apps, each refresh while a list is open
    gives back → TopApps ▶ JSON ▶ page rows (icon, bar, number, sparkline)
    """

    def __init__(self, icon_cache: AppIconCache | None = None) -> None:
        # LEARN: lock = one thread at a time inside "with self._lock"
        #   page calls ▶ each on its own thread ▶ can overlap
        #   ✗ no lock → two refreshes mix up the recent values
        self._lock = threading.Lock()

        # LEARN: cache = do slow work once, reuse the result after
        #   app icon → small picture = slow ▶ made once per app, reused
        #   "x or y" → use the one passed in (tests: a fake), else a real one
        self._icon_cache = icon_cache or AppIconCache()

        # per-app recent values → each row's sparkline
        self._recent_cpu_by_app = RecentValuesPerApp()
        self._recent_memory_by_app = RecentValuesPerApp()
        self._cpu_count = psutil.cpu_count() or 1

    def read_top_apps(self, limit: int) -> TopApps:
        # LEARN: clamp → force into 1..20
        #   max(limit, 1) → at least 1; min(…, 20) → at most 20
        #   ✓ a bad value from the page can't ask for 0 or 1000 rows
        limit = min(max(limit, 1), MAX_TOP_APPS)
        with self._lock:
            apps = group_process_samples_by_app(
                samples=self.read_process_samples(), cpu_count=self._cpu_count
            )
            by_cpu = pick_top_apps(apps=apps, limit=limit, rank_by="cpu")
            by_memory = pick_top_apps(apps=apps, limit=limit, rank_by="memory")

            for app in by_cpu:
                self._recent_cpu_by_app.add_sample(app.key, app.cpu_percent)

            for app in by_memory:
                self._recent_memory_by_app.add_sample(app.key, float(app.memory_bytes))

            # forget apps that left the lists (else memory grows forever)
            # LEARN: {x for x in items} = set comprehension (a set of unique x)
            self._recent_cpu_by_app.keep_only_apps({app.key for app in by_cpu})
            self._recent_memory_by_app.keep_only_apps({app.key for app in by_memory})

            return TopApps(
                by_cpu=[
                    self._build_app_usage(app=app, recent=self._recent_cpu_by_app)
                    for app in by_cpu
                ],
                by_memory=[
                    self._build_app_usage(app=app, recent=self._recent_memory_by_app)
                    for app in by_memory
                ],
                memory_total_bytes=psutil.virtual_memory().total,
            )

    def read_process_samples(self) -> list[ProcessSample]:
        """
        LEARN: one ProcessSample per running program

        called by → read_top_apps, every refresh while a list is open

        per-program CPU also needs TWO readings (change since last time)
          psutil keeps each process object between scans → compares with
          the last scan; a brand-new program shows 0 % once
        """
        samples = []
        # LEARN: process_iter([...]) = loop over every running process,
        #   pre-reading those fields into process.info (a dict)
        for process in psutil.process_iter(["pid", "name", "exe"]):
            try:
                # LEARN: oneshot() = read the process info once for all the
                #   lines inside, instead of once per line ✓ faster
                with process.oneshot():
                    cpu = process.cpu_percent(interval=None)
                    # rss = "resident set size" = RAM the process uses now
                    memory = process.memory_info().rss
            # skipped quietly:
            #   NoSuchProcess → it quit during the scan
            #   AccessDenied → a system process we may not read (no admin)
            #   ZombieProcess → finished but not cleaned up yet
            except psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess:
                continue

            samples.append(
                ProcessSample(
                    pid=process.info["pid"],
                    name=process.info["name"] or f"pid {process.info['pid']}",
                    exe=process.info["exe"],
                    cpu_percent=cpu,
                    memory_bytes=memory,
                )
            )

        return samples

    def _build_app_usage(self, app: AppTotals, recent: RecentValuesPerApp) -> AppUsage:
        # icon only for real apps (a bundle path); plain programs get None
        #   → the page shows a generic terminal icon instead
        icon = (
            self._icon_cache.get_app_icon_data_url(app.bundle_path)
            if app.bundle_path
            else None
        )
        return AppUsage(
            key=app.key,
            name=app.name,
            is_app=app.bundle_path is not None,
            icon=icon,
            cpu_percent=app.cpu_percent,
            memory_bytes=app.memory_bytes,
            history=recent.values_for(app.key),
        )
