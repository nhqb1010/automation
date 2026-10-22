"""Drive usage: main disk, external drives, network drives and disk images."""

import logging
import plistlib
import subprocess
import threading
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from pathlib import PurePosixPath

import psutil
from Foundation import (
    NSURL,
    NSURLVolumeAvailableCapacityForImportantUsageKey,
    NSURLVolumeAvailableCapacityKey,
    NSURLVolumeLocalizedNameKey,
    NSURLVolumeTotalCapacityKey,
)

from app.tools.system_monitor.models import DriveKind, DriveUsage, StorageStats

logger = logging.getLogger(__name__)

ROOT_MOUNTPOINT = "/"
USER_VOLUMES_DIR = PurePosixPath("/Volumes")
# Time Machine snapshots and other system mounts use these folder names
HIDDEN_VOLUME_NAME_PREFIXES = (".", "com.apple.")
HDIUTIL_PATH = "/usr/bin/hdiutil"
NETWORK_FILESYSTEMS = frozenset({"smbfs", "afpfs", "nfs", "webdav", "cifs", "ftp"})
DRIVE_READ_TIMEOUT_SECONDS = 2.0
DRIVE_KIND_ORDER: dict[DriveKind, int] = {
    "main": 0,
    "external": 1,
    "network": 2,
    "image": 3,
}


@dataclass(frozen=True)
class MountedVolume:
    mountpoint: str
    fstype: str


@dataclass(frozen=True)
class VolumeDetails:
    name: str
    total_bytes: int
    available_bytes: int


def is_user_visible_mountpoint(mountpoint: str) -> bool:
    """
    Tell whether a mount point is a drive the user would recognise.

    LEARN: real drives mount directly under /Volumes (/Volumes/T7). During a
    backup, Time Machine mounts snapshots deeper down, under folders like
    /Volumes/com.apple.TimeMachine.localsnapshots, so both depth and name
    are checked.

    Args:
        mountpoint (str): where the volume is mounted.
    Returns:
        bool: True for the main disk and ordinary drives under /Volumes.
    """
    if mountpoint == ROOT_MOUNTPOINT:
        return True

    path = PurePosixPath(mountpoint)
    if path.parent != USER_VOLUMES_DIR:
        return False

    return not path.name.startswith(HIDDEN_VOLUME_NAME_PREFIXES)


def select_user_visible_volumes(volumes: list[MountedVolume]) -> list[MountedVolume]:
    """
    Keep the main disk and drives directly under /Volumes; skip system mounts.

    LEARN: macOS splits the main disk into many hidden volumes (VM, Preboot,
    Update, Data, ...). They all share one storage pool, so the root volume
    alone already reports the numbers Finder shows for Macintosh HD.

    Args:
        volumes (list[MountedVolume]): every mount point psutil reports.
    Returns:
        list[MountedVolume]: one entry per drive the user would recognise.
    """
    seen: set[str] = set()
    selected = []
    for volume in volumes:
        if (
            is_user_visible_mountpoint(volume.mountpoint)
            and volume.mountpoint not in seen
        ):
            seen.add(volume.mountpoint)
            selected.append(volume)

    return selected


def classify_drive_kind(
    volume: MountedVolume, disk_image_mountpoints: set[str]
) -> DriveKind:
    if volume.mountpoint == ROOT_MOUNTPOINT:
        return "main"
    if volume.fstype in NETWORK_FILESYSTEMS:
        return "network"
    if volume.mountpoint in disk_image_mountpoints:
        return "image"

    return "external"


def build_drive_usage(
    volume: MountedVolume, kind: DriveKind, details: VolumeDetails | None
) -> DriveUsage:
    if details is None:
        return DriveUsage(
            name=PurePosixPath(volume.mountpoint).name or volume.mountpoint,
            mountpoint=volume.mountpoint,
            kind=kind,
            responding=False,
        )

    total = details.total_bytes
    free = min(details.available_bytes, total)
    used = total - free
    return DriveUsage(
        name=details.name,
        mountpoint=volume.mountpoint,
        kind=kind,
        responding=True,
        total_bytes=total,
        used_bytes=used,
        free_bytes=free,
        used_percent=(used / total * 100) if total else 0.0,
    )


def sort_drives_for_display(drives: list[DriveUsage]) -> list[DriveUsage]:
    return sorted(drives, key=lambda drive: (DRIVE_KIND_ORDER[drive.kind], drive.name))


def parse_disk_image_mountpoints(hdiutil_plist: bytes) -> set[str]:
    info = plistlib.loads(hdiutil_plist)
    return {
        entity["mount-point"]
        for image in info.get("images", [])
        for entity in image.get("system-entities", [])
        if "mount-point" in entity
    }


def read_mounted_volumes() -> list[MountedVolume]:
    # LEARN: psutil lists mounts without touching the drives themselves, so a
    # hung network share cannot freeze this call.
    return [
        MountedVolume(mountpoint=partition.mountpoint, fstype=partition.fstype)
        for partition in psutil.disk_partitions(all=True)
    ]


def read_disk_image_mountpoints() -> set[str]:
    try:
        result = subprocess.run(
            [HDIUTIL_PATH, "info", "-plist"],
            capture_output=True,
            check=True,
            timeout=5,
        )
        return parse_disk_image_mountpoints(result.stdout)
    except (
        OSError,
        subprocess.SubprocessError,
        plistlib.InvalidFileException,
    ) as error:
        logger.warning(f"Could not list mounted disk images {error=}")
        return set()


def read_volume_details(mountpoint: str) -> VolumeDetails:
    """
    Read a drive's name, size and free space the way Finder does.

    LEARN: "available for important usage" counts purgeable space (iCloud
    caches and the like) as free, which is what Finder shows. Network drives
    do not report it, so the plain available figure is the fallback.

    Args:
        mountpoint (str): where the drive is mounted.
    Returns:
        VolumeDetails: name, total and available bytes.
    """
    url = NSURL.fileURLWithPath_(mountpoint)
    values, error = url.resourceValuesForKeys_error_(
        [
            NSURLVolumeLocalizedNameKey,
            NSURLVolumeTotalCapacityKey,
            NSURLVolumeAvailableCapacityForImportantUsageKey,
            NSURLVolumeAvailableCapacityKey,
        ],
        None,
    )
    if values is None:
        raise OSError(f"Could not read volume {mountpoint}: {error}")

    available = values.get(NSURLVolumeAvailableCapacityForImportantUsageKey)
    if not available:
        available = values.get(NSURLVolumeAvailableCapacityKey) or 0

    return VolumeDetails(
        name=str(
            values.get(NSURLVolumeLocalizedNameKey) or PurePosixPath(mountpoint).name
        ),
        total_bytes=int(values.get(NSURLVolumeTotalCapacityKey) or 0),
        available_bytes=int(available),
    )


def start_volume_details_read(mountpoint: str) -> Future[VolumeDetails]:
    """
    Read one drive on its own background thread and return a handle to the result.

    LEARN: a daemon thread does not keep the app alive at exit. A read stuck on
    a dead network share therefore cannot stop the app from quitting, and one
    stuck drive never blocks another, unlike a small shared pool of workers.

    Args:
        mountpoint (str): where the drive is mounted.
    Returns:
        Future[VolumeDetails]: completes when the read finishes or fails.
    """
    future: Future[VolumeDetails] = Future()

    def read_volume_details_into_future() -> None:
        try:
            future.set_result(read_volume_details(mountpoint))
        except Exception as error:
            future.set_exception(error)

    threading.Thread(
        target=read_volume_details_into_future,
        name=f"storage-read {mountpoint}",
        daemon=True,
    ).start()
    return future


class StorageReader:
    """
    Reads every drive, giving each one a short time limit.

    LEARN: each drive is read on its own thread, at most one read per drive at
    a time. If a network share does not answer within the limit, the drive
    shows as not responding and the rest of the tool keeps going. A still-stuck
    read is not retried until it finishes. Problems are logged once per drive,
    not on every refresh.
    """

    def __init__(self, timeout_seconds: float = DRIVE_READ_TIMEOUT_SECONDS) -> None:
        self._timeout_seconds = timeout_seconds
        self._pending: dict[str, Future[VolumeDetails]] = {}
        self._drives_with_problems: set[str] = set()
        self._lock = threading.Lock()

    def read_storage_stats(self) -> StorageStats:
        with self._lock:
            volumes = select_user_visible_volumes(read_mounted_volumes())
            disk_images = read_disk_image_mountpoints()
            for volume in volumes:
                self._start_volume_read_if_idle(volume.mountpoint)

            # LEARN: all drives share one deadline, so five hung shares cost one
            # time limit in total instead of one each.
            deadline = time.monotonic() + self._timeout_seconds
            drives = [
                build_drive_usage(
                    volume=volume,
                    kind=classify_drive_kind(volume, disk_images),
                    details=self._wait_for_volume_details(
                        mountpoint=volume.mountpoint, deadline=deadline
                    ),
                )
                for volume in volumes
            ]
            self._forget_unmounted_drives({volume.mountpoint for volume in volumes})
            return StorageStats(drives=sort_drives_for_display(drives))

    def _start_volume_read_if_idle(self, mountpoint: str) -> None:
        future = self._pending.get(mountpoint)
        if future is None or future.done():
            self._pending[mountpoint] = start_volume_details_read(mountpoint)

    def _wait_for_volume_details(
        self, mountpoint: str, deadline: float
    ) -> VolumeDetails | None:
        future = self._pending[mountpoint]
        try:
            details = future.result(timeout=max(deadline - time.monotonic(), 0))
        except FutureTimeoutError:
            self._record_drive_problem(mountpoint, problem="not responding")
            return None
        except Exception as error:
            self._pending.pop(mountpoint, None)
            self._record_drive_problem(mountpoint, problem=f"read failed: {error}")
            return None

        self._pending.pop(mountpoint, None)
        self._record_drive_recovered(mountpoint)
        return details

    def _record_drive_problem(self, mountpoint: str, problem: str) -> None:
        if mountpoint in self._drives_with_problems:
            return

        self._drives_with_problems.add(mountpoint)
        logger.warning(f"Drive problem {mountpoint=} {problem=}")

    def _record_drive_recovered(self, mountpoint: str) -> None:
        if mountpoint not in self._drives_with_problems:
            return

        self._drives_with_problems.discard(mountpoint)
        logger.info(f"Drive responding again {mountpoint=}")

    def _forget_unmounted_drives(self, mounted: set[str]) -> None:
        self._pending = {
            mountpoint: future
            for mountpoint, future in self._pending.items()
            if mountpoint in mounted
        }
        self._drives_with_problems &= mounted
