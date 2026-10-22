"""CPU and RAM usage."""

import logging
import subprocess
import threading
from dataclasses import dataclass

import psutil

from app.tools.system_monitor.history import RollingHistory
from app.tools.system_monitor.models import CoreKind, CoreUsage, CpuStats, MemoryStats

logger = logging.getLogger(__name__)

SYSCTL_PATH = "/usr/sbin/sysctl"
PERFORMANCE_CORE_COUNT_KEY = "hw.perflevel0.logicalcpu"
EFFICIENCY_CORE_COUNT_KEY = "hw.perflevel1.logicalcpu"


@dataclass(frozen=True)
class CoreLayout:
    performance_cores: int
    efficiency_cores: int


@dataclass(frozen=True)
class MemoryReading:
    total_bytes: int
    available_bytes: int
    swap_used_bytes: int
    swap_total_bytes: int


def read_sysctl_integer(key: str) -> int | None:
    try:
        result = subprocess.run(
            [SYSCTL_PATH, "-n", key],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
    except OSError, subprocess.SubprocessError:
        return None

    value = result.stdout.strip()
    return int(value) if value.isdigit() else None


def read_core_layout() -> CoreLayout:
    """
    Ask macOS how many performance and efficiency cores this chip has.

    Returns:
        CoreLayout: the counts, or zeros when macOS does not report them.
    """
    return CoreLayout(
        performance_cores=read_sysctl_integer(PERFORMANCE_CORE_COUNT_KEY) or 0,
        efficiency_cores=read_sysctl_integer(EFFICIENCY_CORE_COUNT_KEY) or 0,
    )


def label_core_kinds(core_count: int, layout: CoreLayout) -> list[CoreKind]:
    """
    Label each logical core as performance (P) or efficiency (E).

    LEARN: on Apple Silicon the efficiency cores come first (cores 0 and 1 on
    an M1 Pro); confirmed on this machine through the cluster type of each
    core in the macOS device tree. If the counts do not add up, every core
    gets a neutral label instead of a wrong one.

    Args:
        core_count (int): how many logical cores psutil reports.
        layout (CoreLayout): performance and efficiency counts from macOS.
    Returns:
        list[CoreKind]: one label per core, in core order.
    """
    if layout.performance_cores + layout.efficiency_cores != core_count:
        return ["?"] * core_count

    return ["E"] * layout.efficiency_cores + ["P"] * layout.performance_cores


def build_cpu_stats(
    per_core_percents: list[float],
    load_average: tuple[float, float, float],
    layout: CoreLayout,
    history: list[float],
) -> CpuStats:
    kinds = label_core_kinds(core_count=len(per_core_percents), layout=layout)
    total = (
        sum(per_core_percents) / len(per_core_percents) if per_core_percents else 0.0
    )
    return CpuStats(
        percent=total,
        cores=[
            CoreUsage(index=index, kind=kind, percent=percent)
            for index, (kind, percent) in enumerate(zip(kinds, per_core_percents))
        ],
        load_average=load_average,
        performance_cores=layout.performance_cores,
        efficiency_cores=layout.efficiency_cores,
        history=history,
    )


def build_memory_stats(reading: MemoryReading, history: list[float]) -> MemoryStats:
    # LEARN: used is total minus available, so used and percent always agree.
    # Activity Monitor counts cached and compressed memory its own way, so its
    # number will be close but not identical.
    return MemoryStats(
        total_bytes=reading.total_bytes,
        used_bytes=calculate_used_memory_bytes(reading),
        available_bytes=reading.available_bytes,
        percent=calculate_memory_percent(reading),
        swap_used_bytes=reading.swap_used_bytes,
        swap_total_bytes=reading.swap_total_bytes,
        history=history,
    )


def calculate_used_memory_bytes(reading: MemoryReading) -> int:
    return max(reading.total_bytes - reading.available_bytes, 0)


def calculate_memory_percent(reading: MemoryReading) -> float:
    if not reading.total_bytes:
        return 0.0

    return calculate_used_memory_bytes(reading) / reading.total_bytes * 100


class CpuMemoryReader:
    """Reads live CPU and RAM numbers and keeps their short histories."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._layout = read_core_layout()
        self._cpu_history = RollingHistory()
        self._memory_history = RollingHistory()
        # LEARN: psutil measures CPU as the change since the previous call, so
        # the very first call has nothing to compare against and returns 0.
        # Calling it once here "primes" it for the first real refresh.
        psutil.cpu_percent(interval=None, percpu=True)
        logger.info(f"CPU layout {self._layout=}")

    def read_cpu_stats(self) -> CpuStats:
        with self._lock:
            per_core = psutil.cpu_percent(interval=None, percpu=True)
            load_1, load_5, load_15 = psutil.getloadavg()
            stats = build_cpu_stats(
                per_core_percents=per_core,
                load_average=(load_1, load_5, load_15),
                layout=self._layout,
                history=[],
            )
            self._cpu_history.add_sample(stats.percent)
            return stats.model_copy(update={"history": self._cpu_history.values()})

    def read_memory_stats(self) -> MemoryStats:
        with self._lock:
            virtual = psutil.virtual_memory()
            swap = psutil.swap_memory()
            reading = MemoryReading(
                total_bytes=virtual.total,
                available_bytes=virtual.available,
                swap_used_bytes=swap.used,
                swap_total_bytes=swap.total,
            )
            self._memory_history.add_sample(calculate_memory_percent(reading))
            return build_memory_stats(
                reading=reading, history=self._memory_history.values()
            )
