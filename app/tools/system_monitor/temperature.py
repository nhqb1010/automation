"""
CPU and GPU temperature on Apple Silicon.

All the risky code lives here: it talks to undocumented macOS sensor APIs.
If anything fails, the tool reports temperature as unavailable instead of crashing.

LEARN: two sources, tried in order.

  SMC chip ──▶ keys like Tp09 / Tg05 ──▶ real CPU and GPU split   (preferred)
      │ fails or no keys
      ▼
  IOHID hub ──▶ names like PMU tdie3 ──▶ one "Chip" reading        (fallback)
"""

import ctypes
import ctypes.util
import logging
import struct
import threading
from dataclasses import dataclass
from functools import cache
from typing import Literal, Protocol

from app.tools.system_monitor.history import RollingHistory
from app.tools.system_monitor.models import TemperatureStats

logger = logging.getLogger(__name__)

type TemperatureSource = Literal["cpu_gpu", "chip"]

MIN_VALID_CELSIUS = 10.0
MAX_VALID_CELSIUS = 130.0

# LEARN: SMC keys are four letters. The prefix says what is measured:
# Tp = CPU performance cores (and efficiency cores on M1), Te = efficiency
# cores on later chips, Tg = GPU. Community projects (Stats, Asahi Linux)
# documented these; Apple never did.
CPU_SMC_KEY_PREFIXES = ("Tp", "Te")
GPU_SMC_KEY_PREFIX = "Tg"
CHIP_DIE_SENSOR_PREFIX = "PMU tdie"

_SMC_SERVICE_NAME = b"AppleSMC"
_SMC_KERNEL_INDEX = 2
_SMC_COMMAND_READ_BYTES = 5
_SMC_COMMAND_READ_INDEX = 8
_SMC_COMMAND_READ_KEY_INFO = 9
_SMC_FLOAT_TYPE = "flt "
_SMC_FLOAT_SIZE = 4
_SMC_KEY_COUNT_KEY = "#KEY"

# LEARN: the IOHID sensor hub lists thermal sensors under vendor usage page
# 0xff00, usage 5. Matching on those two numbers returns only thermometers.
_HID_USAGE_PAGE = 0xFF00
_HID_USAGE_TEMPERATURE = 5
_HID_EVENT_TYPE_TEMPERATURE = 15
_HID_TEMPERATURE_FIELD = _HID_EVENT_TYPE_TEMPERATURE << 16
_CF_STRING_ENCODING_UTF8 = 0x08000100
_CF_NUMBER_SINT32 = 3
_SENSOR_NAME_BUFFER_SIZE = 256


class TemperatureUnavailableError(RuntimeError):
    """A sensor API could not be opened on this Mac."""


@dataclass(frozen=True)
class SensorReading:
    name: str
    celsius: float


@dataclass(frozen=True)
class TemperatureSummary:
    source: TemperatureSource
    cpu_hottest: float
    cpu_average: float
    gpu_hottest: float | None


class SensorReader(Protocol):
    def read_sensor_readings(self) -> list[SensorReading]: ...


def keep_plausible_readings(readings: list[SensorReading]) -> list[SensorReading]:
    return [
        reading
        for reading in readings
        if MIN_VALID_CELSIUS <= reading.celsius <= MAX_VALID_CELSIUS
    ]


def summarize_smc_temperature_readings(
    readings: list[SensorReading],
) -> TemperatureSummary | None:
    """
    Split SMC readings into CPU and GPU numbers.

    Args:
        readings (list[SensorReading]): SMC readings named by their four letter key.
    Returns:
        TemperatureSummary | None: the summary, or None when no CPU key was found.
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
    Turn IOHID die sensors into one whole chip reading (the fallback).

    Args:
        readings (list[SensorReading]): IOHID readings named like PMU tdie3.
    Returns:
        TemperatureSummary | None: the summary, or None when no die sensor was found.
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
    """CoreFoundation, IOKit and libSystem loaded once, with C signatures declared."""

    def __init__(self) -> None:
        self.core_foundation = _load_macos_library("CoreFoundation")
        self.iokit = _load_macos_library("IOKit")
        self.system = _load_macos_library("System")
        _declare_core_foundation_signatures(self.core_foundation)
        _declare_iokit_signatures(self.iokit)


@cache
def _load_mac_frameworks() -> _MacFrameworks:
    return _MacFrameworks()


def _load_macos_library(name: str) -> ctypes.CDLL:
    path = ctypes.util.find_library(name)
    if not path:
        raise TemperatureUnavailableError(f"{name} library not found")

    return ctypes.CDLL(path)


def _declare_core_foundation_signatures(cf: ctypes.CDLL) -> None:
    # LEARN: ctypes assumes every C function takes and returns int unless told
    # otherwise. Pointers are 64 bit, so without these declarations they would
    # be cut in half and crash the process.
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


# LEARN: these structs mirror the C layout the SMC driver expects, byte for
# byte (80 bytes in total). ctypes adds the same padding a C compiler would.
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
    # LEARN: a key like Tp09 travels as a 32 bit number: its four ASCII bytes
    # read big endian (a "four character code").
    return int.from_bytes(key.encode("ascii"), "big")


def decode_smc_key(value: int) -> str:
    return value.to_bytes(4, "big").decode("ascii", errors="replace")


class SmcSensorReader:
    """
    Reads CPU and GPU temperature keys from the System Management Controller.

    LEARN: talking to the SMC is a request and reply of one fixed size struct.
    Fill in a key and a command number, hand it to the driver, read the reply.

      request: key=Tp09, command=read bytes ──▶ AppleSMC driver
      reply:   bytes=[4 byte float]          ◀──
    """

    def __init__(self) -> None:
        self._frameworks = _load_mac_frameworks()
        self._connection = self._open_smc_connection()
        self._temperature_keys = self._find_temperature_keys()
        if not self._temperature_keys:
            raise TemperatureUnavailableError("no SMC temperature keys found")

    def read_sensor_readings(self) -> list[SensorReading]:
        return [
            SensorReading(name=key, celsius=celsius)
            for key in self._temperature_keys
            if (celsius := self._read_float_key(key)) is not None
        ]

    def _open_smc_connection(self) -> int:
        iokit = self._frameworks.iokit
        # LEARN: IOServiceMatching builds a search for the AppleSMC driver;
        # IOServiceOpen then gives us a connection handle to talk to it.
        # Main port 0 means the default one, no admin rights involved.
        service = iokit.IOServiceGetMatchingService(
            0, iokit.IOServiceMatching(_SMC_SERVICE_NAME)
        )
        if not service:
            raise TemperatureUnavailableError("AppleSMC service not found")

        connection = ctypes.c_uint32(0)
        task = ctypes.c_uint32.in_dll(self._frameworks.system, "mach_task_self_")
        result = iokit.IOServiceOpen(service, task.value, 0, ctypes.byref(connection))
        iokit.IOObjectRelease(service)
        if result != 0:
            raise TemperatureUnavailableError(f"could not open AppleSMC {result=}")

        return connection.value

    def _find_temperature_keys(self) -> list[str]:
        key_count = self._read_key_count()
        temperature_keys = []
        for index in range(key_count):
            key = self._read_key_at_index(index)
            if key is None or not key.startswith(
                (*CPU_SMC_KEY_PREFIXES, GPU_SMC_KEY_PREFIX)
            ):
                continue

            info = self._read_key_info(key)
            if info and info == (_SMC_FLOAT_TYPE, _SMC_FLOAT_SIZE):
                temperature_keys.append(key)

        logger.info(f"SMC temperature keys found {len(temperature_keys)=}")
        return temperature_keys

    def _read_key_count(self) -> int:
        info = self._read_key_info(_SMC_KEY_COUNT_KEY)
        if info is None:
            return 0

        _, size = info
        raw = self._read_key_bytes(key=_SMC_KEY_COUNT_KEY, size=size)
        return int.from_bytes(raw, "big") if raw else 0

    def _read_key_at_index(self, index: int) -> str | None:
        request = _SmcKeyData(command=_SMC_COMMAND_READ_INDEX, data32=index)
        reply = self._call_smc(request)
        return decode_smc_key(reply.key) if reply else None

    def _read_key_info(self, key: str) -> tuple[str, int] | None:
        request = _SmcKeyData(
            key=encode_smc_key(key), command=_SMC_COMMAND_READ_KEY_INFO
        )
        reply = self._call_smc(request)
        if reply is None:
            return None

        return decode_smc_key(reply.key_info.data_type), reply.key_info.data_size

    def _read_key_bytes(self, key: str, size: int) -> bytes | None:
        request = _SmcKeyData(key=encode_smc_key(key), command=_SMC_COMMAND_READ_BYTES)
        request.key_info.data_size = size
        reply = self._call_smc(request)
        return bytes(reply.bytes[:size]) if reply else None

    def _read_float_key(self, key: str) -> float | None:
        raw = self._read_key_bytes(key=key, size=_SMC_FLOAT_SIZE)
        if raw is None:
            return None

        # LEARN: on Apple Silicon these values are little endian 32 bit floats.
        (celsius,) = struct.unpack("<f", raw)
        return celsius

    def _call_smc(self, request: _SmcKeyData) -> _SmcKeyData | None:
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
    Reads every temperature sensor through the IOHID event system (the fallback).

    LEARN: anything a Create or Copy call hands back is ours to release;
    otherwise it leaks on every refresh.
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
        services = self._frameworks.iokit.IOHIDEventSystemClientCopyServices(
            self._client
        )
        if not services:
            return []

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
            if name_ref:
                cf.CFRelease(name_ref)
            if event:
                cf.CFRelease(event)

    def _apply_temperature_sensor_matching(self) -> None:
        cf = self._frameworks.core_foundation
        keys = [
            self._create_cf_string("PrimaryUsagePage"),
            self._create_cf_string("PrimaryUsage"),
        ]
        values = [
            self._create_cf_number(_HID_USAGE_PAGE),
            self._create_cf_number(_HID_USAGE_TEMPERATURE),
        ]
        key_array = (ctypes.c_void_p * 2)(*keys)
        value_array = (ctypes.c_void_p * 2)(*values)
        # LEARN: CFDictionaryCreate needs the address of Apple's standard
        # callback structs so the dictionary knows how to retain its contents.
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
            cf.CFRelease(matching)
            for ref in [*keys, *values]:
                cf.CFRelease(ref)

    def _create_cf_string(self, text: str) -> int:
        return self._frameworks.core_foundation.CFStringCreateWithCString(
            None, text.encode(), _CF_STRING_ENCODING_UTF8
        )

    def _create_cf_number(self, value: int) -> int:
        number = ctypes.c_int32(value)
        return self._frameworks.core_foundation.CFNumberCreate(
            None, _CF_NUMBER_SINT32, ctypes.byref(number)
        )

    def _read_cf_string(self, ref: int) -> str:
        buffer = ctypes.create_string_buffer(_SENSOR_NAME_BUFFER_SIZE)
        ok = self._frameworks.core_foundation.CFStringGetCString(
            ref, buffer, _SENSOR_NAME_BUFFER_SIZE, _CF_STRING_ENCODING_UTF8
        )
        return buffer.value.decode(errors="replace") if ok else ""


class TemperatureMonitor:
    """Picks the best working sensor source and keeps history for the sparklines."""

    def __init__(
        self,
        smc_reader: SensorReader | None = None,
        hid_reader: SensorReader | None = None,
        open_real_sensors: bool = True,
    ) -> None:
        self._lock = threading.Lock()
        self._cpu_history = RollingHistory()
        self._gpu_history = RollingHistory()
        self._last_source: TemperatureSource | None = None
        self._unavailable_reason: str | None = None
        self._logged_reasons: set[str] = set()
        self._smc_reader = smc_reader
        self._hid_reader = hid_reader
        if open_real_sensors and smc_reader is None:
            self._smc_reader = self._open_sensor_reader(SmcSensorReader, label="SMC")
        if open_real_sensors and hid_reader is None:
            self._hid_reader = self._open_sensor_reader(HidSensorReader, label="IOHID")

    def read_temperature_stats(self) -> TemperatureStats:
        with self._lock:
            summary = self._read_smc_summary() or self._read_chip_die_summary()
            if summary is None:
                return TemperatureStats(
                    available=False,
                    reason=self._unavailable_reason or "no temperature sensors found",
                )

            if summary.source != self._last_source:
                logger.info(f"Temperature source in use {summary.source=}")
                self._last_source = summary.source

            self._cpu_history.add_sample(summary.cpu_hottest)
            if summary.gpu_hottest is not None:
                self._gpu_history.add_sample(summary.gpu_hottest)

            return TemperatureStats(
                available=True,
                source=summary.source,
                cpu_hottest=summary.cpu_hottest,
                cpu_average=summary.cpu_average,
                gpu_hottest=summary.gpu_hottest,
                cpu_history=self._cpu_history.values(),
                gpu_history=self._gpu_history.values(),
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

        try:
            return reader.read_sensor_readings()
        except Exception as error:
            self._record_unavailable_reason(f"{label} read failed: {error}")
            return []

    def _open_sensor_reader(
        self, reader_class: type[SensorReader], label: str
    ) -> SensorReader | None:
        try:
            return reader_class()
        except Exception as error:
            self._record_unavailable_reason(f"{label} unavailable: {error}")
            return None

    def _record_unavailable_reason(self, reason: str) -> None:
        self._unavailable_reason = reason
        if reason not in self._logged_reasons:
            logger.warning(f"Temperature sensor problem {reason=}")
            self._logged_reasons.add(reason)
