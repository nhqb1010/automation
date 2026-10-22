import pytest

from app.tools.system_monitor.temperature import (
    SensorReading,
    TemperatureMonitor,
    decode_smc_key,
    encode_smc_key,
    summarize_chip_die_readings,
    summarize_smc_temperature_readings,
)


class FakeSensorReader:
    def __init__(
        self, readings: list[SensorReading] | None = None, fail: bool = False
    ) -> None:
        self._readings = readings or []
        self._fail = fail

    def read_sensor_readings(self) -> list[SensorReading]:
        if self._fail:
            raise OSError("sensor gone")

        return self._readings


class TestSystemMonitorTemperatureSummarizeSmcReadings:
    def test_system_monitor_temperature_smc_splits_cpu_gpu_and_drops_junk(
        self, fake_smc_readings: list[SensorReading]
    ) -> None:
        summary = summarize_smc_temperature_readings(fake_smc_readings)

        assert summary is not None
        assert summary.source == "cpu_gpu"
        assert summary.cpu_hottest == 60.0
        assert summary.cpu_average == pytest.approx(50.0)
        assert summary.gpu_hottest == 47.0

    def test_system_monitor_temperature_smc_none_without_cpu_keys(self) -> None:
        readings = [SensorReading(name="Tg05", celsius=45.0)]

        assert summarize_smc_temperature_readings(readings) is None


class TestSystemMonitorTemperatureSummarizeChipDieReadings:
    def test_system_monitor_temperature_chip_die_uses_die_sensors_only(
        self, fake_hid_readings: list[SensorReading]
    ) -> None:
        summary = summarize_chip_die_readings(fake_hid_readings)

        assert summary is not None
        assert summary.source == "chip"
        assert summary.cpu_hottest == 38.0
        assert summary.gpu_hottest is None


class TestSystemMonitorTemperatureSmcKeyCodes:
    def test_system_monitor_temperature_smc_key_round_trip(self) -> None:
        assert decode_smc_key(encode_smc_key("Tp09")) == "Tp09"
        assert encode_smc_key("#KEY") == 0x234B4559


class TestSystemMonitorTemperatureMonitor:
    def test_system_monitor_temperature_monitor_prefers_smc(
        self,
        fake_smc_readings: list[SensorReading],
        fake_hid_readings: list[SensorReading],
    ) -> None:
        monitor = TemperatureMonitor(
            smc_reader=FakeSensorReader(fake_smc_readings),
            hid_reader=FakeSensorReader(fake_hid_readings),
            open_real_sensors=False,
        )

        stats = monitor.read_temperature_stats()

        assert stats.available
        assert stats.source == "cpu_gpu"
        assert stats.cpu_history == [60.0]
        assert stats.gpu_history == [47.0]

    def test_system_monitor_temperature_monitor_falls_back_to_chip(
        self, fake_hid_readings: list[SensorReading]
    ) -> None:
        monitor = TemperatureMonitor(
            smc_reader=FakeSensorReader(fail=True),
            hid_reader=FakeSensorReader(fake_hid_readings),
            open_real_sensors=False,
        )

        stats = monitor.read_temperature_stats()

        assert stats.available
        assert stats.source == "chip"
        assert stats.cpu_hottest == 38.0

    def test_system_monitor_temperature_monitor_unavailable_with_reason(self) -> None:
        monitor = TemperatureMonitor(
            smc_reader=FakeSensorReader(fail=True),
            hid_reader=None,
            open_real_sensors=False,
        )

        stats = monitor.read_temperature_stats()

        assert not stats.available
        assert "SMC read failed" in (stats.reason or "")
