# LEARN: YOU ARE HERE
#   page opens System Monitor ▶ bridge.call("get_mac_info")
#   ▶ system_monitor/__init__.py ▶ THIS FILE asks macOS what Mac this is
#   ▶ MacInfo ▶ JSON ▶ the This Mac card
#   read next → app/tools/system_monitor/top_apps.py
"""
Which Mac this is, and how old: model, chip, memory, macOS, set-up date, uptime.

LEARN: where each value comes from (no password needed)

  model name   ioreg device tree "product-name"  "MacBook Pro (14-inch, 2021)"
                 (the name About This Mac shows)
  chip, RAM    system_profiler SPHardwareDataType  "Apple M1 Pro", "16 GB"
  macOS        platform.mac_ver()                  "26.6.2"
  set up       date of /private/var/db/.AppleSetupDone
                 (macOS writes it when the first-start setup finishes)
  last start   psutil.boot_time()

  these never change while the app runs → read once, then kept
  industry term: "memoization" / caching a value that can't change
"""

import json
import logging
import platform
import plistlib
import re
import subprocess
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any

import psutil

from app.tools.system_monitor.models import MacInfo

logger = logging.getLogger(__name__)

IOREG_PATH = "/usr/sbin/ioreg"
SYSTEM_PROFILER_PATH = "/usr/sbin/system_profiler"
SETUP_DONE_FILE = Path("/private/var/db/.AppleSetupDone")
COMMAND_TIMEOUT_SECONDS = 5
# LEARN: regex for a 4-digit year: \b = a word edge, (?:19|20) = "19" or "20",
#   \d{2} = two more digits → finds "2021" in "MacBook Pro (14-inch, 2021)"
MODEL_YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b")


def run_command_output(command: list[str]) -> bytes | None:
    """
    LEARN: run one fixed macOS tool, give back its output (or None on any error)

    called by → read_product_name, read_hardware_overview
    a missing value is fine here → the card shows "—", the app carries on
    """
    try:
        result = subprocess.run(
            command, capture_output=True, check=True, timeout=COMMAND_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.SubprocessError) as error:
        logger.warning(f"Mac info command failed {command[0]=} {error=}")
        return None

    return result.stdout


def read_product_name() -> str | None:
    """
    LEARN: the marketing name, e.g. "MacBook Pro (14-inch, 2021)"

    ioreg -a (plist) -r -d1 (only matching entries, one level) -k product-name
    the value is raw bytes ending in a zero byte → strip it, decode as text
    """
    output = run_command_output([IOREG_PATH, "-a", "-r", "-d1", "-k", "product-name"])
    if not output:
        return None

    try:
        entries = plistlib.loads(output)
    except ValueError:
        return None

    for entry in entries:
        value = entry.get("product-name")
        if isinstance(value, bytes):
            return value.rstrip(b"\x00").decode("utf-8", errors="replace") or None
        if isinstance(value, str):
            return value or None

    return None


def read_hardware_overview() -> dict[str, Any]:
    """
    LEARN: the Hardware section of System Information, as a dict

    system_profiler … -json → {"SPHardwareDataType": [{ "chip_type": …, … }]}
    nothing readable → {} (every value then shows "—")
    """
    output = run_command_output([SYSTEM_PROFILER_PATH, "SPHardwareDataType", "-json"])
    if not output:
        return {}

    try:
        sections = json.loads(output).get("SPHardwareDataType") or [{}]
    except ValueError:
        return {}

    return sections[0] if isinstance(sections[0], dict) else {}


def read_setup_date(setup_done_file: Path = SETUP_DONE_FILE) -> date | None:
    """
    LEARN: the date macOS finished its first-start setup on this Mac

    st_mtime = when the file was last changed, in seconds since 1970
    datetime.fromtimestamp(seconds).date() → just the day
    """
    try:
        return datetime.fromtimestamp(setup_done_file.stat().st_mtime).date()
    except OSError:
        return None


def find_model_year(model_name: str | None) -> int | None:
    # "MacBook Pro (14-inch, 2021)" → 2021; no year in the name → None
    if not model_name:
        return None

    match = MODEL_YEAR_PATTERN.search(model_name)
    return int(match.group()) if match else None


def count_whole_months_between(start: date, end: date) -> int:
    """
    LEARN: full months from start to end

      4 Aug 2023 → 29 Oct 2026 = 38 months (3 yrs 2 mo)
      a month only counts once its day is reached: 4 Aug → 3 Sep = 0
    """
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day < start.day:
        months -= 1

    return max(0, months)


@dataclass(frozen=True)
class MacDetailsReading:
    """
    LEARN: everything macOS told us, before it's turned into the card's shape

    made by → MacInfoReader, once (the boot time is refreshed on each read)
    used by → build_mac_info
    """

    product_name: str | None
    hardware: dict[str, Any]
    macos_version: str | None
    setup_date: date | None
    boot_time: float | None


def build_mac_info(reading: MacDetailsReading, today: date) -> MacInfo:
    """
    LEARN: put the pieces together for the card

    called by → MacInfoReader.read_mac_info (and tests, with fixed values)
    today is passed in (not read inside) → tests always get the same answer
    """
    # no marketing name (e.g. an older Mac) → the plain name, "MacBook Pro"
    model_name = reading.product_name or reading.hardware.get("machine_name")
    model_year = find_model_year(model_name)
    setup_date = reading.setup_date
    return MacInfo(
        model_name=model_name,
        model_identifier=reading.hardware.get("machine_model"),
        # Apple Silicon reports "chip_type"; older Intel Macs "cpu_type"
        chip=reading.hardware.get("chip_type") or reading.hardware.get("cpu_type"),
        memory=reading.hardware.get("physical_memory"),
        macos_version=reading.macos_version or None,
        model_year=model_year,
        model_age_years=today.year - model_year if model_year else None,
        setup_date=setup_date.isoformat() if setup_date else None,
        months_since_setup=(
            count_whole_months_between(setup_date, today) if setup_date else None
        ),
        boot_time=reading.boot_time,
    )


class MacInfoReader:
    """
    LEARN: asks macOS once, then reuses the answer

    made by → SystemMonitorTool, once at startup
    called by → SystemMonitorTool.get_mac_info, each time the page opens
    the ages are worked out fresh each time → right even if the app stays
    open for days
    """

    def __init__(self) -> None:
        self._reading: MacDetailsReading | None = None

    def read_mac_info(self) -> MacInfo:
        # the slow part (two macOS tools) runs only the first time
        if self._reading is None:
            self._reading = MacDetailsReading(
                product_name=read_product_name(),
                hardware=read_hardware_overview(),
                # platform.mac_ver() → ("26.6.2", …); [0] = the version
                macos_version=platform.mac_ver()[0],
                setup_date=read_setup_date(),
                boot_time=None,
            )

        # LEARN: replace(obj, field=value) → a copy of a frozen dataclass
        #   with one field changed (frozen ones can't be changed in place)
        reading = replace(self._reading, boot_time=psutil.boot_time())
        return build_mac_info(reading=reading, today=date.today())
