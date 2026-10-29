# LEARN: YOU ARE HERE
#   page refresh ▶ bridge ▶ System Monitor tool ▶ THIS FILE reads CPU + RAM
#   ▶ CpuStats / MemoryStats ▶ JSON ▶ CPU card + Memory card on the page
#   read next → app/tools/system_monitor/recent_values.py
"""CPU and RAM usage."""

import logging
import subprocess
import threading
from dataclasses import dataclass

# LEARN: psutil = third-party library that reads system numbers
#   (CPU %, memory, processes, disks) on macOS, Linux and Windows
import psutil

from app.tools.system_monitor.models import CoreKind, CoreUsage, CpuStats, MemoryStats
from app.tools.system_monitor.recent_values import RecentValues

# LEARN: one logger per file, named after the module (app.tools...cpu_memory)
#   → every log line shows which file wrote it
logger = logging.getLogger(__name__)

# LEARN: sysctl = macOS command that prints hardware facts
#   full path (/usr/sbin/...) → runs the real tool, not a look-alike on PATH
SYSCTL_PATH = "/usr/sbin/sysctl"
PERFORMANCE_CORE_COUNT_KEY = "hw.perflevel0.logicalcpu"
EFFICIENCY_CORE_COUNT_KEY = "hw.perflevel1.logicalcpu"


# LEARN: @dataclass = decorator that writes __init__ for you from the fields
#   CoreLayout(performance_cores=6, efficiency_cores=2) just works
#   frozen=True → fields can't be changed after creation (read-only record)
#
# LEARN: decorator = the @name line above a class / function
#   it wraps or adds behaviour to what's below it
@dataclass(frozen=True)
class CoreLayout:
    """LEARN: how many Performance (fast) and Efficiency (low-power) cores."""

    performance_cores: int
    efficiency_cores: int


@dataclass(frozen=True)
class MemoryReading:
    """LEARN: raw memory numbers from psutil, before any maths."""

    total_bytes: int
    available_bytes: int
    swap_used_bytes: int
    swap_total_bytes: int


def read_sysctl_integer(key: str) -> int | None:
    """
    LEARN: run "sysctl -n <key>" and read back one whole number

    called by → read_core_layout, once at startup
    gives back → the number, or None if macOS doesn't know that key

    int | None = "a whole number OR nothing"
    """
    # LEARN: try / except = run something that may fail, catch the failure
    #   instead of crashing
    try:
        # LEARN: subprocess.run = start another program and wait for it
        #   [program, arg, arg] → the command, as a list (no shell involved)
        #   capture_output=True → keep what it prints, don't show it
        #   text=True → give the output as text, not raw bytes
        #   check=True → treat a failing command as an error
        #   timeout=2 → give up after 2 s
        result = subprocess.run(
            [SYSCTL_PATH, "-n", key],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
    # LEARN: "except A, B:" = catch either error type (Python 3.14 form of
    #   "except (A, B):")
    #   OSError → the program couldn't start
    #   SubprocessError → it failed or timed out
    except OSError, subprocess.SubprocessError:
        return None

    # .strip() → remove spaces / newline around the printed text
    value = result.stdout.strip()

    # .isdigit() → True only if every character is 0-9
    return int(value) if value.isdigit() else None


def read_core_layout() -> CoreLayout:
    """
    LEARN: ask macOS how many P and E cores this chip has

    called by → CpuMemoryReader, once at startup
    gives back → CoreLayout (zeros if macOS doesn't say)
    """
    # LEARN: "x or 0" → use x, but 0 if x is None (or 0 / empty)
    return CoreLayout(
        performance_cores=read_sysctl_integer(PERFORMANCE_CORE_COUNT_KEY) or 0,
        efficiency_cores=read_sysctl_integer(EFFICIENCY_CORE_COUNT_KEY) or 0,
    )


def label_core_kinds(core_count: int, layout: CoreLayout) -> list[CoreKind]:
    """
    LEARN: label every core "P" or "E"

    called by → build_cpu_stats, every refresh
    gives back → one label per core, in core order, e.g. E E P P P P P P

    on Apple Silicon the efficiency cores come first (0 and 1 on an M1 Pro)
      ✓ checked on this Mac via each core's cluster type in the device tree

    counts don't add up (other Mac / unknown chip) → "?" for every core
      ✓ a neutral label is better than a wrong one
    """
    if layout.performance_cores + layout.efficiency_cores != core_count:
        # LEARN: ["?"] * 8 → a list with "?" repeated 8 times
        return ["?"] * core_count

    # LEARN: + on two lists → one longer list: ["E", "E"] + ["P", "P"]
    return ["E"] * layout.efficiency_cores + ["P"] * layout.performance_cores


def build_cpu_stats(
    per_core_percents: list[float],
    load_average: tuple[float, float, float],
    layout: CoreLayout,
    history: list[float],
) -> CpuStats:
    """
    LEARN: turn raw CPU numbers into the CpuStats the page draws

    called by → CpuMemoryReader.read_cpu_stats (and tests, with fake numbers)
    gives back → CpuStats ▶ JSON ▶ CPU card (ring, core columns, sparkline)

    kept separate from the psutil call on purpose
      → pure maths: same input = same output ✓ easy to test
    """
    kinds = label_core_kinds(core_count=len(per_core_percents), layout=layout)

    # total CPU % = average of all cores (0 if there are none)
    total = (
        sum(per_core_percents) / len(per_core_percents) if per_core_percents else 0.0
    )
    return CpuStats(
        percent=total,
        # LEARN: zip(a, b) → pairs items up: (a[0], b[0]), (a[1], b[1]) …
        #   enumerate(x) → adds a counter: (0, item), (1, item) …
        #   together → (index, (kind, percent)) for every core
        #   same as:
        #     cores = []
        #     for index in range(len(kinds)):
        #         cores.append(CoreUsage(index, kinds[index], percents[index]))
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
    """
    LEARN: turn raw memory numbers into the MemoryStats the page draws

    called by → CpuMemoryReader.read_memory_stats (and tests)
    gives back → MemoryStats ▶ JSON ▶ Memory card (ring, used / total, swap)

    used = total − available → used and % always agree
    Activity Monitor counts cached / compressed memory its own way
      → its number is close, not identical
    """
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
    # LEARN: max(x, 0) → never below 0, even if the numbers are odd
    return max(reading.total_bytes - reading.available_bytes, 0)


def calculate_memory_percent(reading: MemoryReading) -> float:
    # total unknown (0) → 0 %, instead of dividing by zero (a crash)
    if not reading.total_bytes:
        return 0.0

    return calculate_used_memory_bytes(reading) / reading.total_bytes * 100


class CpuMemoryReader:
    """
    LEARN: reads live CPU + RAM and keeps ~60 s of each for the sparklines

    made by → the System Monitor tool, once at startup
    called by → the tool's get_live_stats, every refresh (default every 2 s)
    """

    def __init__(self) -> None:
        # LEARN: Lock = only one thread at a time inside "with self._lock:"
        #   each call from the page runs on its own thread (pywebview does this)
        #   → two refreshes can overlap
        #   ✗ no lock → both change the recent values at once and mix them up
        #   industry term: "race condition" (what the lock prevents)
        self._lock = threading.Lock()
        self._layout = read_core_layout()
        self._recent_cpu_percents = RecentValues()
        self._recent_memory_percents = RecentValues()

        # LEARN: psutil measures CPU as the CHANGE since its previous call
        #   first call ever → nothing to compare → returns 0
        #   calling it once now = "priming" → the first real refresh is right
        psutil.cpu_percent(interval=None, percpu=True)

        # LEARN: f"...{x=}" → writes "x=<value>" into the text (handy in logs)
        logger.info(f"CPU layout {self._layout=}")

    def read_cpu_stats(self) -> CpuStats:
        # LEARN: with lock: → take the lock, run the block, release it
        #   (released even if the block crashes)
        with self._lock:
            # interval=None → don't wait; compare with the previous call
            # percpu=True → one % per core, e.g. [50.0, 51.0, 11.0, …]
            per_core = psutil.cpu_percent(interval=None, percpu=True)

            # LEARN: load average = how many tasks wanted the CPU, averaged
            #   over the last 1, 5 and 15 minutes
            # LEARN: a, b, c = (1, 2, 3) → "unpacking": one value per name
            load_1, load_5, load_15 = psutil.getloadavg()

            stats = build_cpu_stats(
                per_core_percents=per_core,
                load_average=(load_1, load_5, load_15),
                layout=self._layout,
                history=[],
            )
            self._recent_cpu_percents.add_sample(stats.percent)

            # LEARN: model_copy(update=...) → a copy of the model with some
            #   fields replaced (pydantic models aren't edited in place here)
            return stats.model_copy(
                update={"history": self._recent_cpu_percents.values()}
            )

    def read_memory_stats(self) -> MemoryStats:
        with self._lock:
            virtual = psutil.virtual_memory()
            # LEARN: swap = disk space used as extra memory when RAM is full
            #   (much slower than RAM)
            swap = psutil.swap_memory()
            reading = MemoryReading(
                total_bytes=virtual.total,
                available_bytes=virtual.available,
                swap_used_bytes=swap.used,
                swap_total_bytes=swap.total,
            )
            self._recent_memory_percents.add_sample(calculate_memory_percent(reading))
            return build_memory_stats(
                reading=reading, history=self._recent_memory_percents.values()
            )
