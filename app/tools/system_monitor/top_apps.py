"""Which apps use the most CPU and RAM, helpers grouped under their app."""

import logging
import threading
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

import psutil

from app.tools.system_monitor.app_icons import AppIconCache
from app.tools.system_monitor.history import KeyedRollingHistory
from app.tools.system_monitor.models import AppUsage, TopApps

logger = logging.getLogger(__name__)

APP_BUNDLE_SUFFIX = ".app"
MAX_TOP_APPS = 20

type RankBy = Literal["cpu", "memory"]


@dataclass(frozen=True)
class ProcessSample:
    pid: int
    name: str
    exe: str | None
    cpu_percent: float
    memory_bytes: int


@dataclass(frozen=True)
class AppTotals:
    key: str
    name: str
    bundle_path: str | None
    cpu_percent: float
    memory_bytes: int


def find_app_bundle_path(exe: str | None) -> str | None:
    """
    Find the outermost .app folder a program lives in.

    LEARN: helpers live inside their app, for example
    Google Chrome.app/.../Google Chrome Helper (Renderer).app/...
    Taking the outermost .app groups every helper under Google Chrome.

    Args:
        exe (str | None): full path of the program, None when macOS hides it.
    Returns:
        str | None: the bundle path, or None when the program is not in an app.
    """
    if not exe:
        return None

    parts = PurePosixPath(exe).parts
    for index, part in enumerate(parts):
        if part.endswith(APP_BUNDLE_SUFFIX):
            return str(PurePosixPath(*parts[: index + 1]))

    return None


def group_process_samples_by_app(
    samples: list[ProcessSample], cpu_count: int
) -> list[AppTotals]:
    """
    Add up CPU and RAM per app; processes outside any app keep their own name.

    LEARN: macOS reports process CPU per core (one busy core = 100%). Dividing
    by the core count turns it into a share of the whole CPU, matching the
    main CPU ring.

    Args:
        samples (list[ProcessSample]): one sample per running process.
        cpu_count (int): number of logical cores.
    Returns:
        list[AppTotals]: one entry per app or standalone process.
    """
    divisor = max(cpu_count, 1)
    totals: dict[str, AppTotals] = {}
    for sample in samples:
        bundle_path = find_app_bundle_path(sample.exe)
        key = bundle_path or f"process:{sample.name}"
        name = PurePosixPath(bundle_path).stem if bundle_path else sample.name
        current = totals.get(key)
        totals[key] = AppTotals(
            key=key,
            name=name,
            bundle_path=bundle_path,
            cpu_percent=(current.cpu_percent if current else 0.0)
            + sample.cpu_percent / divisor,
            memory_bytes=(current.memory_bytes if current else 0) + sample.memory_bytes,
        )

    return list(totals.values())


def pick_top_apps(
    apps: list[AppTotals], limit: int, rank_by: RankBy
) -> list[AppTotals]:
    match rank_by:
        case "cpu":
            ranked = sorted(apps, key=lambda app: app.cpu_percent, reverse=True)
        case "memory":
            ranked = sorted(apps, key=lambda app: app.memory_bytes, reverse=True)

    return ranked[:limit]


class TopAppsReader:
    """Scans running processes and ranks apps; keeps per-app sparkline history."""

    def __init__(self, icon_cache: AppIconCache | None = None) -> None:
        self._lock = threading.Lock()
        self._icon_cache = icon_cache or AppIconCache()
        self._cpu_history = KeyedRollingHistory()
        self._memory_history = KeyedRollingHistory()
        self._cpu_count = psutil.cpu_count() or 1

    def read_top_apps(self, limit: int) -> TopApps:
        limit = min(max(limit, 1), MAX_TOP_APPS)
        with self._lock:
            apps = group_process_samples_by_app(
                samples=self.read_process_samples(), cpu_count=self._cpu_count
            )
            by_cpu = pick_top_apps(apps=apps, limit=limit, rank_by="cpu")
            by_memory = pick_top_apps(apps=apps, limit=limit, rank_by="memory")

            for app in by_cpu:
                self._cpu_history.add_sample(app.key, app.cpu_percent)

            for app in by_memory:
                self._memory_history.add_sample(app.key, float(app.memory_bytes))

            self._cpu_history.keep_only_keys({app.key for app in by_cpu})
            self._memory_history.keep_only_keys({app.key for app in by_memory})

            return TopApps(
                by_cpu=[
                    self._build_app_usage(app=app, history=self._cpu_history)
                    for app in by_cpu
                ],
                by_memory=[
                    self._build_app_usage(app=app, history=self._memory_history)
                    for app in by_memory
                ],
                memory_total_bytes=psutil.virtual_memory().total,
            )

    def read_process_samples(self) -> list[ProcessSample]:
        # LEARN: per-process CPU also needs two readings. psutil keeps the
        # process objects between scans, so each scan compares against the
        # last one. A process seen for the first time shows 0% once.
        samples = []
        for process in psutil.process_iter(["pid", "name", "exe"]):
            try:
                with process.oneshot():
                    cpu = process.cpu_percent(interval=None)
                    memory = process.memory_info().rss
            except psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess:
                # system processes refuse access without admin rights, and apps
                # can exit mid-scan; both are skipped quietly
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

    def _build_app_usage(
        self, app: AppTotals, history: KeyedRollingHistory
    ) -> AppUsage:
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
            history=history.values_for(app.key),
        )
