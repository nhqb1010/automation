"""Data shapes the System Monitor sends to its page."""

from typing import Literal

from pydantic import BaseModel

type CoreKind = Literal["P", "E", "?"]
type DriveKind = Literal["main", "external", "network", "image"]


class CoreUsage(BaseModel):
    index: int
    kind: CoreKind
    percent: float


class CpuStats(BaseModel):
    percent: float
    cores: list[CoreUsage]
    load_average: tuple[float, float, float]
    performance_cores: int
    efficiency_cores: int
    history: list[float]


class MemoryStats(BaseModel):
    total_bytes: int
    used_bytes: int
    available_bytes: int
    percent: float
    swap_used_bytes: int
    swap_total_bytes: int
    history: list[float]


class TemperatureStats(BaseModel):
    available: bool
    source: Literal["cpu_gpu", "chip"] | None = None
    reason: str | None = None
    cpu_hottest: float | None = None
    cpu_average: float | None = None
    gpu_hottest: float | None = None
    cpu_history: list[float] = []
    gpu_history: list[float] = []


class LiveStats(BaseModel):
    cpu: CpuStats
    memory: MemoryStats
    temperature: TemperatureStats


class AppUsage(BaseModel):
    key: str
    name: str
    is_app: bool
    icon: str | None
    cpu_percent: float
    memory_bytes: int
    history: list[float]


class TopApps(BaseModel):
    by_cpu: list[AppUsage]
    by_memory: list[AppUsage]
    memory_total_bytes: int


class DriveUsage(BaseModel):
    name: str
    mountpoint: str
    kind: DriveKind
    responding: bool
    total_bytes: int | None = None
    used_bytes: int | None = None
    free_bytes: int | None = None
    used_percent: float | None = None


class StorageStats(BaseModel):
    drives: list[DriveUsage]
