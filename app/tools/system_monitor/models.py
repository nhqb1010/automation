# LEARN: YOU ARE HERE
#   readers (CPU / RAM / temperature / top apps / storage) fill these shapes
#   ▶ bridge turns them into JSON ▶ the page reads the same field names
#   read next → app/tools/system_monitor/cpu_memory.py
"""
Data shapes the System Monitor sends to its page.

LEARN: pydantic model = a class that describes data AND checks it
  CpuStats(percent="abc") → error straight away ✓ bad data never reaches
  the page
  .model_dump() → a plain dict → JSON for the page

LEARN: the field names here = the names the page's JavaScript uses
  Python: stats.cpu.percent   ▶ JSON ▶   JS: stats.cpu.percent
  rename one side → rename the other too

  LiveStats ─┬─ cpu: CpuStats ── cores: [CoreUsage, …]
             ├─ memory: MemoryStats
             └─ temperature: TemperatureStats
  TopApps ── by_cpu / by_memory: [AppUsage, …]
  StorageStats ── drives: [DriveUsage, …]
"""

from typing import Literal

from pydantic import BaseModel

# LEARN: Literal[...] = only these exact values are allowed
#   "P" = performance core, "E" = efficiency core, "?" = unknown
type CoreKind = Literal["P", "E", "?"]
type DriveKind = Literal["main", "external", "network", "image"]


# LEARN: class X(BaseModel) → X inherits pydantic's checking and JSON powers
#   each "name: type" line = one field; no __init__ needed
class CoreUsage(BaseModel):
    """LEARN: one CPU core → one column on the CPU card."""

    index: int
    kind: CoreKind
    percent: float


class CpuStats(BaseModel):
    """LEARN: the whole CPU card: ring %, cores, load, sparkline values."""

    percent: float
    cores: list[CoreUsage]
    # LEARN: tuple[float, float, float] = exactly three decimals (1, 5, 15 min)
    load_average: tuple[float, float, float]
    performance_cores: int
    efficiency_cores: int
    # last ~60 s of percent → the sparkline
    history: list[float]


class MemoryStats(BaseModel):
    """LEARN: the Memory card: ring %, used / total, swap, sparkline values."""

    total_bytes: int
    used_bytes: int
    available_bytes: int
    percent: float
    swap_used_bytes: int
    swap_total_bytes: int
    history: list[float]


class TemperatureStats(BaseModel):
    """
    LEARN: the Temperature card

    available False → greyed card + reason
    source "cpu_gpu" → two gauges; "chip" → one "Chip" gauge (fallback)
    "= None" / "= []" → default when not given (most fields are optional)
    """

    available: bool
    source: Literal["cpu_gpu", "chip"] | None = None
    reason: str | None = None
    cpu_hottest: float | None = None
    cpu_average: float | None = None
    gpu_hottest: float | None = None
    cpu_history: list[float] = []
    gpu_history: list[float] = []


class LiveStats(BaseModel):
    """LEARN: everything one live refresh sends, in one package."""

    cpu: CpuStats
    memory: MemoryStats
    temperature: TemperatureStats


class AppUsage(BaseModel):
    """
    LEARN: one row in a Top apps list

    icon = picture as text ("data:image/png;base64,…") or None
    history = that app's recent values → the row's sparkline
    """

    key: str
    name: str
    is_app: bool
    icon: str | None
    cpu_percent: float
    memory_bytes: int
    history: list[float]


class TopApps(BaseModel):
    """LEARN: both Top apps lists + total RAM (to turn bytes into a %)."""

    by_cpu: list[AppUsage]
    by_memory: list[AppUsage]
    memory_total_bytes: int


class DriveUsage(BaseModel):
    """
    LEARN: one donut in the Storage card

    responding False → "Not responding", the size fields stay None
    """

    name: str
    mountpoint: str
    kind: DriveKind
    responding: bool
    total_bytes: int | None = None
    used_bytes: int | None = None
    free_bytes: int | None = None
    used_percent: float | None = None


class StorageStats(BaseModel):
    """LEARN: all drives, already sorted (main disk first)."""

    drives: list[DriveUsage]
