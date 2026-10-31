# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks mac_info.py (model, ages) with fixed values
#   (no real macOS tools are run)
#   read next → tests/test_system_monitor_tool.py
import json
import os
import plistlib
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.tools.system_monitor import mac_info
from app.tools.system_monitor.mac_info import (
    MacDetailsReading,
    MacInfoReader,
    build_mac_info,
    count_whole_months_between,
    find_model_year,
    read_hardware_overview,
    read_product_name,
    read_setup_date,
)

TODAY = date(2026, 10, 29)
HARDWARE = {
    "machine_name": "MacBook Pro",
    "machine_model": "MacBookPro18,3",
    "chip_type": "Apple M1 Pro",
    "physical_memory": "16 GB",
}


def make_reading(**changes: Any) -> MacDetailsReading:
    # the real Mac's values; **changes overrides any of them per test
    values: dict[str, Any] = {
        "product_name": "MacBook Pro (14-inch, 2021)",
        "hardware": HARDWARE,
        "macos_version": "26.6.2",
        "setup_date": date(2023, 8, 4),
        "boot_time": 1_790_000_000.0,
    }
    return MacDetailsReading(**{**values, **changes})


class TestSystemMonitorMacInfoFindModelYear:
    def test_system_monitor_mac_info_find_model_year(self) -> None:
        assert find_model_year("MacBook Pro (14-inch, 2021)") == 2021
        assert find_model_year("MacBook Pro") is None
        assert find_model_year(None) is None


class TestSystemMonitorMacInfoCountWholeMonthsBetween:
    def test_system_monitor_mac_info_count_whole_months_between(self) -> None:
        assert count_whole_months_between(date(2023, 8, 4), TODAY) == 38
        # the 4th hasn't come round yet → still 0 months
        assert count_whole_months_between(date(2023, 8, 4), date(2023, 9, 3)) == 0
        assert count_whole_months_between(date(2023, 8, 4), date(2023, 9, 4)) == 1


class TestSystemMonitorMacInfoBuildMacInfo:
    def test_system_monitor_mac_info_build_mac_info_full(self) -> None:
        info = build_mac_info(reading=make_reading(), today=TODAY)

        assert info.model_name == "MacBook Pro (14-inch, 2021)"
        assert info.chip == "Apple M1 Pro"
        assert info.memory == "16 GB"
        assert info.model_age_years == 5
        assert info.setup_date == "2023-08-04"
        assert info.months_since_setup == 38

    def test_system_monitor_mac_info_build_mac_info_missing_values(self) -> None:
        reading = make_reading(
            product_name=None, hardware={}, macos_version="", setup_date=None
        )

        info = build_mac_info(reading=reading, today=TODAY)

        assert info.model_name is None
        assert info.model_year is None
        assert info.macos_version is None
        assert info.months_since_setup is None

    def test_system_monitor_mac_info_build_mac_info_falls_back_to_plain_name(
        self,
    ) -> None:
        info = build_mac_info(reading=make_reading(product_name=None), today=TODAY)

        assert info.model_name == "MacBook Pro"
        assert info.model_age_years is None


class TestSystemMonitorMacInfoReadProductName:
    def test_system_monitor_mac_info_read_product_name_strips_zero_byte(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        output = plistlib.dumps([{"product-name": b"MacBook Pro (14-inch, 2021)\x00"}])
        monkeypatch.setattr(mac_info, "run_command_output", lambda command: output)

        assert read_product_name() == "MacBook Pro (14-inch, 2021)"

    def test_system_monitor_mac_info_read_product_name_command_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mac_info, "run_command_output", lambda command: None)

        assert read_product_name() is None


class TestSystemMonitorMacInfoReadHardwareOverview:
    def test_system_monitor_mac_info_read_hardware_overview(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        output = json.dumps({"SPHardwareDataType": [HARDWARE]}).encode()
        monkeypatch.setattr(mac_info, "run_command_output", lambda command: output)

        assert read_hardware_overview()["chip_type"] == "Apple M1 Pro"

    def test_system_monitor_mac_info_read_hardware_overview_bad_output(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mac_info, "run_command_output", lambda command: b"{oops")

        assert read_hardware_overview() == {}


class TestSystemMonitorMacInfoReadSetupDate:
    def test_system_monitor_mac_info_read_setup_date(self, tmp_path: Path) -> None:
        marker = tmp_path / ".AppleSetupDone"
        marker.touch()
        # os.utime(path, (access, modified)) → set the file's dates by hand
        seconds = 1_691_150_400  # 4 Aug 2023, midday UTC
        os.utime(marker, (seconds, seconds))

        assert read_setup_date(marker) == date(2023, 8, 4)

    def test_system_monitor_mac_info_read_setup_date_missing(
        self, tmp_path: Path
    ) -> None:
        assert read_setup_date(tmp_path / "missing") is None


class TestSystemMonitorMacInfoReader:
    def test_system_monitor_mac_info_reader_asks_macos_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        def count_product_name_reads() -> str:
            calls.append("product-name")
            return "MacBook Pro (14-inch, 2021)"

        monkeypatch.setattr(mac_info, "read_product_name", count_product_name_reads)
        monkeypatch.setattr(mac_info, "read_hardware_overview", lambda: HARDWARE)
        reader = MacInfoReader()

        reader.read_mac_info()
        info = reader.read_mac_info()

        assert calls == ["product-name"]
        assert info.boot_time is not None
