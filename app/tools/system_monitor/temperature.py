# LEARN: YOU ARE HERE
#   page refresh ▶ bridge ▶ System Monitor tool ▶ THIS FILE reads chip sensors
#   ▶ TemperatureStats ▶ JSON ▶ Temperature card (gauges + sparkline)
#   read next → app/tools/system_monitor/power.py
"""
CPU and GPU temperature on Apple Silicon.

LEARN: the riskiest file in the app
  → talks to macOS sensor APIs Apple never documented
  → if anything fails: temperature shows "unavailable", the app keeps running

LEARN: two sources, tried in order

  SMC chip ──▶ keys like Tp09 / Tg05 ──▶ real CPU + GPU split   (preferred)
      │ fails or finds nothing
      ▼
  IOHID hub ──▶ names like PMU tdie3 ──▶ one "Chip" reading      (fallback)

LEARN: big picture of how Python talks to macOS here

  Python ──ctypes──▶ C functions inside macOS libraries (IOKit, CoreFoundation)

  ctypes = Python's built-in way to call C code directly
    ✓ nothing to install
    ✗ you must describe every C type yourself, or it crashes
"""

import ctypes
import ctypes.util
import logging
import struct
import threading
from dataclasses import dataclass
from functools import cache
from typing import Literal, Protocol

from app.tools.system_monitor.models import TemperatureStats
from app.tools.system_monitor.recent_values import RecentValues

logger = logging.getLogger(__name__)

# LEARN: "type X = ..." = a type alias (a short name for a longer type)
#   Literal["cpu_gpu", "chip"] = only these two exact texts are allowed
type TemperatureSource = Literal["cpu_gpu", "chip"]

# LEARN: sensors sometimes report junk (0 °C, 250 °C) → ignore outside this range
MIN_VALID_CELSIUS = 10.0
MAX_VALID_CELSIUS = 130.0

# LEARN: SMC keys are four letters; the first two say what is measured
#   Tp = CPU performance cores (and efficiency cores on M1)
#   Te = CPU efficiency cores (later chips)
#   Tg = GPU
#   documented by community projects (Stats app, Asahi Linux), never by Apple
#
# LEARN: ("Tp", "Te") = a tuple (a fixed, read-only list)
#   str.startswith(tuple) → True if the text starts with ANY of them
CPU_SMC_KEY_PREFIXES = ("Tp", "Te")
GPU_SMC_KEY_PREFIX = "Tg"
CHIP_DIE_SENSOR_PREFIX = "PMU tdie"

# LEARN: leading _ on module constants = only used inside this file
#   these are numbers the SMC driver understands (its "protocol")
#   b"AppleSMC" = bytes, not text (C functions take raw bytes)
_SMC_SERVICE_NAME = b"AppleSMC"
_SMC_KERNEL_INDEX = 2
_SMC_COMMAND_READ_BYTES = 5
_SMC_COMMAND_READ_INDEX = 8
_SMC_COMMAND_READ_KEY_INFO = 9
_SMC_FLOAT_TYPE = "flt "
_SMC_FLOAT_SIZE = 4
_SMC_KEY_COUNT_KEY = "#KEY"

# LEARN: the IOHID hub lists thermometers under "usage page" 0xff00, usage 5
#   asking for those two numbers → only thermometers come back
#   0xFF00 = hexadecimal (base 16) way of writing 65280
#   15 << 16 = shift 15 left by 16 bits = 15 × 65536 (how the API packs fields)
_HID_USAGE_PAGE = 0xFF00
_HID_USAGE_TEMPERATURE = 5
_HID_EVENT_TYPE_TEMPERATURE = 15
_HID_TEMPERATURE_FIELD = _HID_EVENT_TYPE_TEMPERATURE << 16
_CF_STRING_ENCODING_UTF8 = 0x08000100
_CF_NUMBER_SINT32 = 3
_SENSOR_NAME_BUFFER_SIZE = 256


# LEARN: custom error type = a class that inherits from a built-in error
#   class X(RuntimeError) → X behaves like RuntimeError, but has its own name
#   → callers can catch exactly this problem
class TemperatureUnavailableError(RuntimeError):
    """A sensor API could not be opened on this Mac."""


@dataclass(frozen=True)
class SensorReading:
    """LEARN: one sensor's name + value, e.g. ("Tp09", 48.5)."""

    name: str
    celsius: float


@dataclass(frozen=True)
class TemperatureSummary:
    """LEARN: the few numbers the page needs, boiled down from all sensors."""

    source: TemperatureSource
    cpu_hottest: float
    cpu_average: float
    gpu_hottest: float | None


# LEARN: Protocol = describes a SHAPE, not a parent class
#   "anything with a read_sensor_readings() method counts as a SensorReader"
#   → real readers and the tests' fake readers both fit, no inheritance needed
#   industry term: "duck typing" (if it quacks like a duck…)
#   "..." = an empty body (only the shape matters here)
class SensorReader(Protocol):
    def read_sensor_readings(self) -> list[SensorReading]: ...


def keep_plausible_readings(readings: list[SensorReading]) -> list[SensorReading]:
    # LEARN: a <= x <= b → Python allows chained comparisons ("between")
    return [
        reading
        for reading in readings
        if MIN_VALID_CELSIUS <= reading.celsius <= MAX_VALID_CELSIUS
    ]


def summarize_smc_temperature_readings(
    readings: list[SensorReading],
) -> TemperatureSummary | None:
    """
    LEARN: split SMC readings into CPU and GPU numbers

    called by → TemperatureMonitor, every refresh
    gives back → TemperatureSummary, or None when no CPU key was found
    """
    valid = keep_plausible_readings(readings)
    cpu_values = [r.celsius for r in valid if r.name.startswith(CPU_SMC_KEY_PREFIXES)]
    gpu_values = [r.celsius for r in valid if r.name.startswith(GPU_SMC_KEY_PREFIX)]
    if not cpu_values:
        return None

    return TemperatureSummary(
        source="cpu_gpu",
        cpu_hottest=max(cpu_values),
        cpu_average=sum(cpu_values) / len(cpu_values),
        gpu_hottest=max(gpu_values) if gpu_values else None,
    )


def summarize_chip_die_readings(
    readings: list[SensorReading],
) -> TemperatureSummary | None:
    """
    LEARN: the fallback → one whole-chip number from the IOHID die sensors

    called by → TemperatureMonitor, only when the SMC gave nothing
    gives back → TemperatureSummary (no GPU), or None when nothing was found

    "die" = the silicon chip itself; "tdie" sensors sit on it
    """
    valid = keep_plausible_readings(readings)
    die_values = [r.celsius for r in valid if r.name.startswith(CHIP_DIE_SENSOR_PREFIX)]
    if not die_values:
        return None

    return TemperatureSummary(
        source="chip",
        cpu_hottest=max(die_values),
        cpu_average=sum(die_values) / len(die_values),
        gpu_hottest=None,
    )


class _MacFrameworks:
    """
    LEARN: the three macOS libraries we call into, loaded once

    CoreFoundation → Apple's basic types (text, numbers, lists) in C
    IOKit          → talks to hardware drivers (SMC, sensors)
    System         → core OS functions (we need one value from it)
    """

    def __init__(self) -> None:
        self.core_foundation = _load_macos_library("CoreFoundation")
        self.iokit = _load_macos_library("IOKit")
        self.system = _load_macos_library("System")
        _declare_core_foundation_signatures(self.core_foundation)
        _declare_iokit_signatures(self.iokit)


# LEARN: @cache = remember the result of the first call, reuse it forever
#   → the libraries are loaded once, however many readers ask
#   industry term: "memoization"
@cache
def _load_mac_frameworks() -> _MacFrameworks:
    return _MacFrameworks()


def _load_macos_library(name: str) -> ctypes.CDLL:
    # find_library("IOKit") → the file path of that macOS library
    path = ctypes.util.find_library(name)
    if not path:
        # LEARN: raise = stop here and throw an error up to the caller
        raise TemperatureUnavailableError(f"{name} library not found")

    # CDLL(path) → load the library; its C functions become attributes
    return ctypes.CDLL(path)


def _declare_core_foundation_signatures(cf: ctypes.CDLL) -> None:
    # LEARN: "signature" = what a function takes in and gives back
    #   ctypes can't read C headers, so we tell it by hand:
    #   .argtypes = the input types, .restype = the return type
    #   default guess = "int" → 64-bit pointers get cut in half → crash ✗
    #
    #   c_void_p = a pointer (a memory address, "where something lives")
    #   c_char_p = a C text (bytes ending in a zero byte)
    #   c_uint32 / c_long / c_int = whole numbers of fixed sizes
    pointer = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [pointer, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFStringCreateWithCString.restype = pointer
    cf.CFNumberCreate.argtypes = [pointer, ctypes.c_int, pointer]
    cf.CFNumberCreate.restype = pointer
    cf.CFDictionaryCreate.argtypes = [
        pointer,
        pointer,
        pointer,
        ctypes.c_long,
        pointer,
        pointer,
    ]
    cf.CFDictionaryCreate.restype = pointer
    cf.CFArrayGetCount.argtypes = [pointer]
    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetValueAtIndex.argtypes = [pointer, ctypes.c_long]
    cf.CFArrayGetValueAtIndex.restype = pointer
    cf.CFStringGetCString.argtypes = [
        pointer,
        ctypes.c_char_p,
        ctypes.c_long,
        ctypes.c_uint32,
    ]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFRelease.argtypes = [pointer]
    cf.CFRelease.restype = None


def _declare_iokit_signatures(iokit: ctypes.CDLL) -> None:
    # LEARN: same idea as above, for the IOKit functions we call
    #   port = a handle (a number) macOS uses to refer to a driver / connection
    pointer = ctypes.c_void_p
    port = ctypes.c_uint32

    iokit.IOHIDEventSystemClientCreate.argtypes = [pointer]
    iokit.IOHIDEventSystemClientCreate.restype = pointer
    iokit.IOHIDEventSystemClientSetMatching.argtypes = [pointer, pointer]
    iokit.IOHIDEventSystemClientSetMatching.restype = ctypes.c_int
    iokit.IOHIDEventSystemClientCopyServices.argtypes = [pointer]
    iokit.IOHIDEventSystemClientCopyServices.restype = pointer
    iokit.IOHIDServiceClientCopyProperty.argtypes = [pointer, pointer]
    iokit.IOHIDServiceClientCopyProperty.restype = pointer
    iokit.IOHIDServiceClientCopyEvent.argtypes = [
        pointer,
        ctypes.c_int64,
        ctypes.c_int32,
        ctypes.c_int64,
    ]
    iokit.IOHIDServiceClientCopyEvent.restype = pointer
    iokit.IOHIDEventGetFloatValue.argtypes = [pointer, ctypes.c_uint32]
    iokit.IOHIDEventGetFloatValue.restype = ctypes.c_double

    iokit.IOServiceMatching.argtypes = [ctypes.c_char_p]
    iokit.IOServiceMatching.restype = pointer
    iokit.IOServiceGetMatchingService.argtypes = [port, pointer]
    iokit.IOServiceGetMatchingService.restype = port
    # LEARN: POINTER(port) = "address of a port" → the function writes the
    #   new connection number INTO our variable (an "out parameter")
    iokit.IOServiceOpen.argtypes = [port, port, ctypes.c_uint32, ctypes.POINTER(port)]
    iokit.IOServiceOpen.restype = ctypes.c_int
    iokit.IOServiceClose.argtypes = [port]
    iokit.IOServiceClose.restype = ctypes.c_int
    iokit.IOObjectRelease.argtypes = [port]
    iokit.IOObjectRelease.restype = ctypes.c_int
    iokit.IOConnectCallStructMethod.argtypes = [
        port,
        ctypes.c_uint32,
        pointer,
        ctypes.c_size_t,
        pointer,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    iokit.IOConnectCallStructMethod.restype = ctypes.c_int


# LEARN: ctypes.Structure = a C "struct": fixed fields, fixed sizes, in order
#   the SMC driver expects EXACTLY this byte layout (80 bytes in total)
#   _fields_ = list of (name, C type); ctypes adds the same gaps ("padding")
#   a C compiler would
#   c_uint8 = 1 byte, c_uint16 = 2 bytes, c_uint32 = 4 bytes
class _SmcVersion(ctypes.Structure):
    _fields_ = (
        ("major", ctypes.c_uint8),
        ("minor", ctypes.c_uint8),
        ("build", ctypes.c_uint8),
        ("reserved", ctypes.c_uint8),
        ("release", ctypes.c_uint16),
    )


class _SmcPowerLimits(ctypes.Structure):
    _fields_ = (
        ("version", ctypes.c_uint16),
        ("length", ctypes.c_uint16),
        ("cpu_limit", ctypes.c_uint32),
        ("gpu_limit", ctypes.c_uint32),
        ("memory_limit", ctypes.c_uint32),
    )


class _SmcKeyInfo(ctypes.Structure):
    _fields_ = (
        ("data_size", ctypes.c_uint32),
        ("data_type", ctypes.c_uint32),
        ("data_attributes", ctypes.c_uint8),
    )


# LEARN: the one message format used both ways (request and reply)
#   we fill key + command, the driver fills result + bytes
#   c_uint8 * 32 = a fixed array of 32 bytes (the value comes back here)
class _SmcKeyData(ctypes.Structure):
    _fields_ = (
        ("key", ctypes.c_uint32),
        ("version", _SmcVersion),
        ("power_limits", _SmcPowerLimits),
        ("key_info", _SmcKeyInfo),
        ("result", ctypes.c_uint8),
        ("status", ctypes.c_uint8),
        ("command", ctypes.c_uint8),
        ("data32", ctypes.c_uint32),
        ("bytes", ctypes.c_uint8 * 32),
    )


def encode_smc_key(key: str) -> int:
    # LEARN: "four character code" (industry term, FourCC)
    #   "Tp09" → 4 ASCII bytes → read as ONE 32-bit number
    #   "big" = big endian = first byte is the most significant
    return int.from_bytes(key.encode("ascii"), "big")


def decode_smc_key(value: int) -> str:
    # the reverse: 32-bit number → 4 bytes → "Tp09"
    # errors="replace" → odd bytes become "?" instead of crashing
    return value.to_bytes(4, "big").decode("ascii", errors="replace")


class SmcSensorReader:
    """
    LEARN: reads CPU + GPU temperatures from the SMC chip

    made by → TemperatureMonitor, once at startup
    called by → TemperatureMonitor, every refresh
    gives back → list of SensorReading (key name + °C)

    SMC = System Management Controller: a small chip that watches fans,
    power and temperatures

    talking to it = one fixed-size message out, one back

      request: key=Tp09, command=read bytes ──▶ AppleSMC driver
      reply:   bytes=[4-byte number]        ◀──
    """

    def __init__(self) -> None:
        self._frameworks = _load_mac_frameworks()
        self._connection = self._open_smc_connection()
        # startup: list every SMC key once, keep the temperature ones
        #   (~0.4 s; later reads only ask for these, ~9 ms per refresh)
        self._temperature_keys = self._find_temperature_keys()
        if not self._temperature_keys:
            raise TemperatureUnavailableError("no SMC temperature keys found")

    def read_sensor_readings(self) -> list[SensorReading]:
        # LEARN: := is the "walrus operator" = assign AND use in one go
        #   same as:
        #     result = []
        #     for key in self._temperature_keys:
        #         celsius = self._read_float_key(key)
        #         if celsius is not None:
        #             result.append(SensorReading(key, celsius))
        return [
            SensorReading(name=key, celsius=celsius)
            for key in self._temperature_keys
            if (celsius := self._read_float_key(key)) is not None
        ]

    def _open_smc_connection(self) -> int:
        iokit = self._frameworks.iokit
        # LEARN: two steps to reach a driver
        #   IOServiceMatching("AppleSMC") → a search description
        #   IOServiceGetMatchingService → finds the driver (0 = default port)
        #   no admin rights involved
        service = iokit.IOServiceGetMatchingService(
            0, iokit.IOServiceMatching(_SMC_SERVICE_NAME)
        )
        if not service:
            raise TemperatureUnavailableError("AppleSMC service not found")

        # LEARN: c_uint32(0) = a C number variable; IOServiceOpen writes the
        #   new connection into it via byref (pass "where it lives")
        connection = ctypes.c_uint32(0)
        # mach_task_self_ = "this running program", needed to open a connection
        task = ctypes.c_uint32.in_dll(self._frameworks.system, "mach_task_self_")
        result = iokit.IOServiceOpen(service, task.value, 0, ctypes.byref(connection))
        # done with the search handle → hand it back to macOS
        iokit.IOObjectRelease(service)
        if result != 0:
            raise TemperatureUnavailableError(f"could not open AppleSMC {result=}")

        return connection.value

    def _find_temperature_keys(self) -> list[str]:
        # the SMC holds ~2000 keys; walk them by position, keep T… floats
        key_count = self._read_key_count()
        temperature_keys = []
        for index in range(key_count):
            key = self._read_key_at_index(index)
            # LEARN: (*A, B) = "unpack" tuple A into a new tuple, then add B
            #   (*("Tp", "Te"), "Tg") → ("Tp", "Te", "Tg")
            if key is None or not key.startswith(
                (*CPU_SMC_KEY_PREFIXES, GPU_SMC_KEY_PREFIX)
            ):
                # LEARN: continue = skip to the next loop round
                continue

            info = self._read_key_info(key)
            # only 4-byte decimal numbers ("flt ") are temperatures
            if info and info == (_SMC_FLOAT_TYPE, _SMC_FLOAT_SIZE):
                temperature_keys.append(key)

        logger.info(f"SMC temperature keys found {len(temperature_keys)=}")
        return temperature_keys

    def _read_key_count(self) -> int:
        # the special key "#KEY" holds how many keys exist
        info = self._read_key_info(_SMC_KEY_COUNT_KEY)
        if info is None:
            return 0

        _, size = info
        raw = self._read_key_bytes(key=_SMC_KEY_COUNT_KEY, size=size)
        return int.from_bytes(raw, "big") if raw else 0

    def _read_key_at_index(self, index: int) -> str | None:
        # "which key is at position N?" → its four-letter name
        request = _SmcKeyData(command=_SMC_COMMAND_READ_INDEX, data32=index)
        reply = self._call_smc(request)
        return decode_smc_key(reply.key) if reply else None

    def _read_key_info(self, key: str) -> tuple[str, int] | None:
        # "what type and size is this key's value?" → e.g. ("flt ", 4)
        request = _SmcKeyData(
            key=encode_smc_key(key), command=_SMC_COMMAND_READ_KEY_INFO
        )
        reply = self._call_smc(request)
        if reply is None:
            return None

        return decode_smc_key(reply.key_info.data_type), reply.key_info.data_size

    def _read_key_bytes(self, key: str, size: int) -> bytes | None:
        # "give me this key's value" → raw bytes
        request = _SmcKeyData(key=encode_smc_key(key), command=_SMC_COMMAND_READ_BYTES)
        request.key_info.data_size = size
        reply = self._call_smc(request)
        # LEARN: x[:size] = "slice": the first size items
        return bytes(reply.bytes[:size]) if reply else None

    def _read_float_key(self, key: str) -> float | None:
        raw = self._read_key_bytes(key=key, size=_SMC_FLOAT_SIZE)
        if raw is None:
            return None

        # LEARN: struct.unpack = turn raw bytes into Python numbers
        #   "<f" = little endian ("<") 4-byte decimal ("f" for float)
        #   gives back a tuple; (celsius,) takes its only item
        (celsius,) = struct.unpack("<f", raw)
        return celsius

    def _call_smc(self, request: _SmcKeyData) -> _SmcKeyData | None:
        # LEARN: send the request struct, get the reply struct back
        #   byref(x) = pass where x lives, so the driver can read / write it
        #   sizeof = how many bytes the struct takes (80)
        #   result 0 = "OK" (C functions often return 0 for success)
        reply = _SmcKeyData()
        reply_size = ctypes.c_size_t(ctypes.sizeof(_SmcKeyData))
        result = self._frameworks.iokit.IOConnectCallStructMethod(
            self._connection,
            _SMC_KERNEL_INDEX,
            ctypes.byref(request),
            ctypes.sizeof(_SmcKeyData),
            ctypes.byref(reply),
            ctypes.byref(reply_size),
        )
        if result != 0 or reply.result != 0:
            return None

        return reply


class HidSensorReader:
    """
    LEARN: the fallback sensor source (IOHID sensor hub)

    made by → TemperatureMonitor, once at startup
    called by → TemperatureMonitor, only when the SMC gave nothing
    gives back → list of SensorReading (sensor name + °C)

    memory rule of these Apple C APIs
      anything from a Create… or Copy… function = ours to free (CFRelease)
      ✗ forget → a little memory leaks on EVERY refresh
      industry term: "memory leak", "manual reference counting"
    """

    def __init__(self) -> None:
        self._frameworks = _load_mac_frameworks()
        self._product_key = self._create_cf_string("Product")
        self._client = self._frameworks.iokit.IOHIDEventSystemClientCreate(None)
        if not self._client:
            raise TemperatureUnavailableError("could not create the sensor client")

        self._apply_temperature_sensor_matching()

    def read_sensor_readings(self) -> list[SensorReading]:
        cf = self._frameworks.core_foundation
        # Copy… → a list of sensors we must free afterwards
        services = self._frameworks.iokit.IOHIDEventSystemClientCopyServices(
            self._client
        )
        if not services:
            return []

        # LEARN: try / finally = the finally block ALWAYS runs, even after an
        #   error → the list is always freed
        try:
            readings = [
                reading
                for index in range(cf.CFArrayGetCount(services))
                if (
                    reading := self._read_sensor(
                        cf.CFArrayGetValueAtIndex(services, index)
                    )
                )
            ]
        finally:
            cf.CFRelease(services)

        return readings

    def _read_sensor(self, service: int) -> SensorReading | None:
        cf = self._frameworks.core_foundation
        iokit = self._frameworks.iokit
        name_ref = iokit.IOHIDServiceClientCopyProperty(service, self._product_key)
        event = iokit.IOHIDServiceClientCopyEvent(
            service, _HID_EVENT_TYPE_TEMPERATURE, 0, 0
        )
        try:
            if not name_ref or not event:
                return None

            celsius = iokit.IOHIDEventGetFloatValue(event, _HID_TEMPERATURE_FIELD)
            return SensorReading(name=self._read_cf_string(name_ref), celsius=celsius)
        finally:
            # both came from Copy… → free them (runs even after "return")
            if name_ref:
                cf.CFRelease(name_ref)
            if event:
                cf.CFRelease(event)

    def _apply_temperature_sensor_matching(self) -> None:
        # LEARN: tell the hub "only thermometers please" by handing it a
        #   C dictionary {PrimaryUsagePage: 0xff00, PrimaryUsage: 5}
        cf = self._frameworks.core_foundation
        keys = [
            self._create_cf_string("PrimaryUsagePage"),
            self._create_cf_string("PrimaryUsage"),
        ]
        values = [
            self._create_cf_number(_HID_USAGE_PAGE),
            self._create_cf_number(_HID_USAGE_TEMPERATURE),
        ]
        # LEARN: (c_void_p * 2)(*keys) = a C array of 2 pointers filled from
        #   the Python list (*keys spreads the list into separate arguments)
        key_array = (ctypes.c_void_p * 2)(*keys)
        value_array = (ctypes.c_void_p * 2)(*values)
        # LEARN: the dictionary needs Apple's standard "how to keep / free
        #   items" helpers; we pass the address where they live in the library
        key_callbacks = ctypes.addressof(
            ctypes.c_char.in_dll(cf, "kCFTypeDictionaryKeyCallBacks")
        )
        value_callbacks = ctypes.addressof(
            ctypes.c_char.in_dll(cf, "kCFTypeDictionaryValueCallBacks")
        )
        matching = cf.CFDictionaryCreate(
            None, key_array, value_array, 2, key_callbacks, value_callbacks
        )
        try:
            self._frameworks.iokit.IOHIDEventSystemClientSetMatching(
                self._client, matching
            )
        finally:
            # everything above came from Create… → free it all
            cf.CFRelease(matching)
            for ref in [*keys, *values]:
                cf.CFRelease(ref)

    def _create_cf_string(self, text: str) -> int:
        # Python text → Apple C text (.encode() turns text into bytes)
        return self._frameworks.core_foundation.CFStringCreateWithCString(
            None, text.encode(), _CF_STRING_ENCODING_UTF8
        )

    def _create_cf_number(self, value: int) -> int:
        number = ctypes.c_int32(value)
        return self._frameworks.core_foundation.CFNumberCreate(
            None, _CF_NUMBER_SINT32, ctypes.byref(number)
        )

    def _read_cf_string(self, ref: int) -> str:
        # Apple C text → Python text, via a 256-byte buffer we provide
        buffer = ctypes.create_string_buffer(_SENSOR_NAME_BUFFER_SIZE)
        ok = self._frameworks.core_foundation.CFStringGetCString(
            ref, buffer, _SENSOR_NAME_BUFFER_SIZE, _CF_STRING_ENCODING_UTF8
        )
        return buffer.value.decode(errors="replace") if ok else ""


class TemperatureMonitor:
    """
    LEARN: picks the sensor source that works + keeps ~60 s of history

    made by → the System Monitor tool, once at startup
    called by → the tool's get_live_stats, every refresh
    gives back → TemperatureStats ▶ JSON ▶ Temperature card

    tests pass fake readers + open_real_sensors=False → no real hardware used
    """

    def __init__(
        self,
        smc_reader: SensorReader | None = None,
        hid_reader: SensorReader | None = None,
        open_real_sensors: bool = True,
    ) -> None:
        # lock → one refresh at a time (see the note in cpu_memory.py)
        self._lock = threading.Lock()
        self._recent_cpu_temperatures = RecentValues()
        self._recent_gpu_temperatures = RecentValues()
        self._last_source: TemperatureSource | None = None
        self._unavailable_reason: str | None = None
        # set() = empty set; remembers which problems were already logged
        self._logged_reasons: set[str] = set()
        self._smc_reader = smc_reader
        self._hid_reader = hid_reader
        if open_real_sensors and smc_reader is None:
            self._smc_reader = self._open_sensor_reader(SmcSensorReader, label="SMC")
        if open_real_sensors and hid_reader is None:
            self._hid_reader = self._open_sensor_reader(HidSensorReader, label="IOHID")

    def read_temperature_stats(self) -> TemperatureStats:
        with self._lock:
            # LEARN: "a() or b()" → if a() gives something, use it;
            #   only if it gives None is b() even run (the fallback)
            summary = self._read_smc_summary() or self._read_chip_die_summary()
            if summary is None:
                return TemperatureStats(
                    available=False,
                    reason=self._unavailable_reason or "no temperature sensors found",
                )

            # log only when the source changes, not every refresh
            if summary.source != self._last_source:
                logger.info(f"Temperature source in use {summary.source=}")
                self._last_source = summary.source

            self._recent_cpu_temperatures.add_sample(summary.cpu_hottest)
            if summary.gpu_hottest is not None:
                self._recent_gpu_temperatures.add_sample(summary.gpu_hottest)

            return TemperatureStats(
                available=True,
                source=summary.source,
                cpu_hottest=summary.cpu_hottest,
                cpu_average=summary.cpu_average,
                gpu_hottest=summary.gpu_hottest,
                cpu_history=self._recent_cpu_temperatures.values(),
                gpu_history=self._recent_gpu_temperatures.values(),
            )

    def _read_smc_summary(self) -> TemperatureSummary | None:
        readings = self._read_sensor_readings_safely(self._smc_reader, label="SMC")
        return summarize_smc_temperature_readings(readings)

    def _read_chip_die_summary(self) -> TemperatureSummary | None:
        readings = self._read_sensor_readings_safely(self._hid_reader, label="IOHID")
        return summarize_chip_die_readings(readings)

    def _read_sensor_readings_safely(
        self, reader: SensorReader | None, label: str
    ) -> list[SensorReading]:
        if reader is None:
            return []

        # any error → note the reason, return nothing → caller falls back
        try:
            return reader.read_sensor_readings()
        except Exception as error:
            self._record_unavailable_reason(f"{label} read failed: {error}")
            return []

    def _open_sensor_reader(
        self, reader_class: type[SensorReader], label: str
    ) -> SensorReader | None:
        # LEARN: type[X] = "the class X itself", not an object made from it
        #   reader_class() → makes one (e.g. SmcSensorReader())
        try:
            return reader_class()
        except Exception as error:
            self._record_unavailable_reason(f"{label} unavailable: {error}")
            return None

    def _record_unavailable_reason(self, reason: str) -> None:
        self._unavailable_reason = reason
        # each distinct problem logged once, not on every refresh
        if reason not in self._logged_reasons:
            logger.warning(f"Temperature sensor problem {reason=}")
            self._logged_reasons.add(reason)
