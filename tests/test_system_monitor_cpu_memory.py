# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks cpu_memory.py's pure maths (no real Mac needed)
#   read next → tests/test_system_monitor_recent_values.py

# LEARN: only the "build / calculate / label" functions are tested
#   they take plain numbers in, give results out ("pure functions")
#   → the parts that read the real Mac stay thin and untested here
from app.tools.system_monitor.cpu_memory import (
    CoreLayout,
    MemoryReading,
    build_cpu_stats,
    build_memory_stats,
    calculate_memory_percent,
    calculate_used_memory_bytes,
    label_core_kinds,
)


class TestSystemMonitorCpuMemoryLabelCoreKinds:
    def test_system_monitor_cpu_memory_label_core_kinds_efficiency_first(self) -> None:
        layout = CoreLayout(performance_cores=6, efficiency_cores=2)

        # ["P"] * 6 → ["P", "P", "P", "P", "P", "P"]
        assert label_core_kinds(core_count=8, layout=layout) == ["E", "E"] + ["P"] * 6

    def test_system_monitor_cpu_memory_label_core_kinds_neutral_on_mismatch(
        self,
    ) -> None:
        layout = CoreLayout(performance_cores=6, efficiency_cores=2)

        # 6 + 2 ≠ 10 → the layout can't be trusted → "?" for every core
        assert label_core_kinds(core_count=10, layout=layout) == ["?"] * 10


class TestSystemMonitorCpuMemoryBuildCpuStats:
    def test_system_monitor_cpu_memory_build_cpu_stats_averages_cores(self) -> None:
        stats = build_cpu_stats(
            per_core_percents=[10.0, 30.0, 50.0, 70.0],
            load_average=(1.0, 2.0, 3.0),
            layout=CoreLayout(performance_cores=2, efficiency_cores=2),
            history=[20.0],
        )

        assert stats.percent == 40.0
        assert [core.kind for core in stats.cores] == ["E", "E", "P", "P"]
        assert stats.cores[3].percent == 70.0
        assert stats.history == [20.0]

    def test_system_monitor_cpu_memory_build_cpu_stats_no_cores(self) -> None:
        stats = build_cpu_stats(
            per_core_percents=[],
            load_average=(0.0, 0.0, 0.0),
            layout=CoreLayout(performance_cores=0, efficiency_cores=0),
            history=[],
        )

        assert stats.percent == 0.0
        assert stats.cores == []


class TestSystemMonitorCpuMemoryBuildMemoryStats:
    def test_system_monitor_cpu_memory_build_memory_stats_used_from_available(
        self,
    ) -> None:
        reading = MemoryReading(
            total_bytes=16_000,
            available_bytes=6_000,
            swap_used_bytes=1_200,
            swap_total_bytes=2_000,
        )

        stats = build_memory_stats(reading=reading, history=[])

        # used = total − available = 16 000 − 6 000
        assert stats.used_bytes == 10_000
        assert stats.percent == 62.5
        assert stats.swap_used_bytes == 1_200

    def test_system_monitor_cpu_memory_build_memory_stats_zero_total(self) -> None:
        reading = MemoryReading(
            total_bytes=0, available_bytes=0, swap_used_bytes=0, swap_total_bytes=0
        )

        assert calculate_memory_percent(reading) == 0.0
        assert build_memory_stats(reading=reading, history=[]).percent == 0.0


class TestSystemMonitorCpuMemoryCalculateUsedMemoryBytes:
    def test_system_monitor_cpu_memory_calculate_used_memory_bytes_never_negative(
        self,
    ) -> None:
        reading = MemoryReading(
            total_bytes=100, available_bytes=150, swap_used_bytes=0, swap_total_bytes=0
        )

        assert calculate_used_memory_bytes(reading) == 0
        assert calculate_memory_percent(reading) == 0.0
