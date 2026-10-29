# LEARN: YOU ARE HERE
#   page timer (every 30 s) ▶ bridge ▶ System Monitor tool
#   ▶ THIS FILE reads every drive's size + free space
#   ▶ StorageStats ▶ JSON ▶ the donuts in the Storage card
#   read next → app/tools/log_viewer/__init__.py
"""Drive usage: main disk, external drives, network drives and disk images."""

import logging

# LEARN: plist = Apple's settings / data file format (XML); plistlib reads it
import plistlib
import subprocess
import threading
import time

# LEARN: Future = a box that will hold a result LATER
#   one thread puts the result in; another waits for it (with a time limit)
#   industry term: "future" / "promise"
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from pathlib import PurePosixPath

import psutil

# LEARN: Foundation = Apple's core macOS library; NSURL = a file location
#   the NSURLVolume…Key names = which facts about a drive to ask for
#   (same source Finder uses → same numbers Finder shows)
from Foundation import (
    NSURL,
    NSURLVolumeAvailableCapacityForImportantUsageKey,
    NSURLVolumeAvailableCapacityKey,
    NSURLVolumeLocalizedNameKey,
    NSURLVolumeTotalCapacityKey,
)

from app.tools.system_monitor.models import DriveKind, DriveUsage, StorageStats

logger = logging.getLogger(__name__)

# LEARN: mount point = the folder where a drive "appears" in the file system
#   main disk → "/"        USB stick "T7" → "/Volumes/T7"
ROOT_MOUNTPOINT = "/"
USER_VOLUMES_DIR = PurePosixPath("/Volumes")
# Time Machine snapshots and other system mounts use these folder names
HIDDEN_VOLUME_NAME_PREFIXES = (".", "com.apple.")
HDIUTIL_PATH = "/usr/bin/hdiutil"
# LEARN: frozenset = a set that can't be changed (a fixed list of names)
#   these file system types = drives reached over the network (NAS, shares)
NETWORK_FILESYSTEMS = frozenset({"smbfs", "afpfs", "nfs", "webdav", "cifs", "ftp"})
DRIVE_READ_TIMEOUT_SECONDS = 2.0
# display order: main disk first, disk images last
DRIVE_KIND_ORDER: dict[DriveKind, int] = {
    "main": 0,
    "external": 1,
    "network": 2,
    "image": 3,
}


@dataclass(frozen=True)
class MountedVolume:
    """LEARN: one mounted drive: where it is + its file system type."""

    mountpoint: str
    fstype: str


@dataclass(frozen=True)
class VolumeDetails:
    """LEARN: a drive's name and sizes, as Finder reports them."""

    name: str
    total_bytes: int
    available_bytes: int


def is_user_visible_mountpoint(mountpoint: str) -> bool:
    """
    LEARN: is this a drive the user would recognise?

    called by → select_user_visible_volumes, once per mount, every 30 s
    gives back → True for the main disk and drives right under /Volumes

      "/"                                      ✓ main disk
      "/Volumes/T7"                            ✓ a USB drive
      "/Volumes/T7/inner"                      ✗ nested, not a drive
      "/Volumes/com.apple.TimeMachine.…"       ✗ Time Machine snapshot
      "/Volumes/.timemachine"                  ✗ hidden (starts with .)
    """
    if mountpoint == ROOT_MOUNTPOINT:
        return True

    path = PurePosixPath(mountpoint)
    # .parent → the folder it sits in; must be exactly /Volumes
    if path.parent != USER_VOLUMES_DIR:
        return False

    # .name → the last part, e.g. "T7"
    return not path.name.startswith(HIDDEN_VOLUME_NAME_PREFIXES)


def select_user_visible_volumes(volumes: list[MountedVolume]) -> list[MountedVolume]:
    """
    LEARN: keep real drives only, each once

    called by → StorageReader.read_storage_stats, every 30 s

    macOS splits the main disk into many hidden parts (VM, Preboot, Data…)
      all share ONE storage pool → "/" alone already gives Finder's numbers
    """
    # "seen" = mount points already kept → skip duplicates
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
    """
    LEARN: main / network / disk image / external → decides the donut style

    called by → StorageReader.read_storage_stats, once per drive
    """
    if volume.mountpoint == ROOT_MOUNTPOINT:
        return "main"
    if volume.fstype in NETWORK_FILESYSTEMS:
        return "network"
    # disk image = a .dmg file opened like a drive (e.g. an installer)
    if volume.mountpoint in disk_image_mountpoints:
        return "image"

    return "external"


def build_drive_usage(
    volume: MountedVolume, kind: DriveKind, details: VolumeDetails | None
) -> DriveUsage:
    """
    LEARN: raw drive facts → the DriveUsage one donut draws

    called by → StorageReader.read_storage_stats (and tests)
    details None = the drive didn't answer in time → "Not responding"
    """
    if details is None:
        return DriveUsage(
            name=PurePosixPath(volume.mountpoint).name or volume.mountpoint,
            mountpoint=volume.mountpoint,
            kind=kind,
            responding=False,
        )

    total = details.total_bytes
    # min(…) → free can never be more than the total (odd reports happen)
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
    # LEARN: sorting by a tuple (kind order, name)
    #   → first by kind; drives of the same kind → alphabetical by name
    return sorted(drives, key=lambda drive: (DRIVE_KIND_ORDER[drive.kind], drive.name))


def parse_disk_image_mountpoints(hdiutil_plist: bytes) -> set[str]:
    """
    LEARN: pull the mount points out of "hdiutil info" output

    called by → read_disk_image_mountpoints (and tests, with fake data)

    plist shape:
      {"images": [ {"system-entities": [ {"mount-point": "/Volumes/X"} ]} ]}
    """
    info = plistlib.loads(hdiutil_plist)
    # LEARN: set comprehension with TWO for's = a nested loop
    #   same as:
    #     result = set()
    #     for image in info["images"]:
    #         for entity in image["system-entities"]:
    #             if "mount-point" in entity:
    #                 result.add(entity["mount-point"])
    #   .get(key, []) → an empty list if the key is missing (no crash)
    return {
        entity["mount-point"]
        for image in info.get("images", [])
        for entity in image.get("system-entities", [])
        if "mount-point" in entity
    }


def read_mounted_volumes() -> list[MountedVolume]:
    # LEARN: psutil lists mounts WITHOUT touching the drives themselves
    #   ✓ a hung network share can't freeze this call
    #   all=True → include every mount; filtering happens later
    return [
        MountedVolume(mountpoint=partition.mountpoint, fstype=partition.fstype)
        for partition in psutil.disk_partitions(all=True)
    ]


def read_disk_image_mountpoints() -> set[str]:
    # hdiutil = macOS disk image tool; "info -plist" lists open disk images
    # (subprocess.run options explained in cpu_memory.py)
    try:
        result = subprocess.run(
            [HDIUTIL_PATH, "info", "-plist"],
            capture_output=True,
            check=True,
            timeout=5,
        )
        return parse_disk_image_mountpoints(result.stdout)
    # LEARN: "except (A, B, C) as error" → catch any of them, name it "error"
    except (
        OSError,
        subprocess.SubprocessError,
        plistlib.InvalidFileException,
    ) as error:
        logger.warning(f"Could not list mounted disk images {error=}")
        return set()


def read_volume_details(mountpoint: str) -> VolumeDetails:
    """
    LEARN: a drive's name, size and free space, the way Finder does it

    called by → a background thread from start_volume_details_read
    gives back → VolumeDetails, or raises an error if the drive can't be read

    "available for important usage" = Finder's free space
      counts purgeable space (iCloud caches etc.) as free
      network drives don't report it → plain "available" as fallback
    """
    url = NSURL.fileURLWithPath_(mountpoint)
    # LEARN: Objective-C "error out-parameter" pattern
    #   resourceValuesForKeys_error_(keys, None) gives back TWO things:
    #   (values, error) → values is None when something went wrong
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
    LEARN: read one drive on its own background thread; return a Future

    called by → StorageReader, when that drive has no read in progress
    gives back → a Future that gets the result (or the error) later

    thread = a second line of work running at the same time
      → a slow drive doesn't stop the rest of the app

    daemon=True → the thread does NOT keep the app alive at exit
      ✓ a read stuck on a dead network share can't block quitting
    """
    future: Future[VolumeDetails] = Future()

    # LEARN: a function defined inside a function ("closure")
    #   it can use future and mountpoint from the outer function
    def read_volume_details_into_future() -> None:
        try:
            future.set_result(read_volume_details(mountpoint))
        except Exception as error:
            future.set_exception(error)

    # target = the function the thread runs; .start() → it begins now
    threading.Thread(
        target=read_volume_details_into_future,
        name=f"storage-read {mountpoint}",
        daemon=True,
    ).start()
    return future


class StorageReader:
    """
    LEARN: reads every drive, each with a short time limit

    made by → the System Monitor tool, once at startup
    called by → the tool's get_storage, every 30 s while the tool is open
    gives back → StorageStats ▶ JSON ▶ Storage card donuts

    each drive → its own thread, at most ONE read per drive at a time
    a drive that doesn't answer in time → "Not responding", rest carries on
    a stuck read isn't restarted until it finishes
    problems → logged once per drive (+ once when it recovers)

      refresh ─┬─ start read: "/"            ─┐
               ├─ start read: "/Volumes/T7"   ├─ wait up to 2 s TOTAL
               └─ start read: "/Volumes/NAS" ─┘   (one shared deadline)
    """

    def __init__(self, timeout_seconds: float = DRIVE_READ_TIMEOUT_SECONDS) -> None:
        self._timeout_seconds = timeout_seconds
        # mount point → its read that hasn't been collected yet
        self._reads_in_progress: dict[str, Future[VolumeDetails]] = {}
        # mount points already logged as having a problem
        self._drives_with_problems: set[str] = set()
        self._lock = threading.Lock()

    def read_storage_stats(self) -> StorageStats:
        with self._lock:
            volumes = select_user_visible_volumes(read_mounted_volumes())
            disk_images = read_disk_image_mountpoints()

            # step 1: start all reads at once (they run side by side)
            for volume in volumes:
                self._start_volume_read_if_idle(volume.mountpoint)

            # step 2: collect them, all against ONE deadline
            #   → 5 hung shares cost 2 s total, not 2 s each
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
        # no read yet, or the last one finished → start a new one
        # still running (stuck) → leave it, don't pile up more threads
        future = self._reads_in_progress.get(mountpoint)
        if future is None or future.done():
            self._reads_in_progress[mountpoint] = start_volume_details_read(mountpoint)

    def _wait_for_volume_details(
        self, mountpoint: str, deadline: float
    ) -> VolumeDetails | None:
        future = self._reads_in_progress[mountpoint]
        try:
            # .result(timeout=…) → wait at most that long for the result
            #   time left = deadline − now (never below 0)
            details = future.result(timeout=max(deadline - time.monotonic(), 0))
        except FutureTimeoutError:
            # not done in time → keep the read running, show "Not responding"
            self._record_drive_problem(mountpoint, problem="not responding")
            return None
        except Exception as error:
            # the read itself failed → drop it, try again next refresh
            self._reads_in_progress.pop(mountpoint, None)
            self._record_drive_problem(mountpoint, problem=f"read failed: {error}")
            return None

        # .pop(key, None) → remove it, no error if it's already gone
        self._reads_in_progress.pop(mountpoint, None)
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

        # .discard(x) → remove x from the set (no error if missing)
        self._drives_with_problems.discard(mountpoint)
        logger.info(f"Drive responding again {mountpoint=}")

    def _forget_unmounted_drives(self, mounted: set[str]) -> None:
        # drives that were unplugged → forget their reads and problems
        self._reads_in_progress = {
            mountpoint: future
            for mountpoint, future in self._reads_in_progress.items()
            if mountpoint in mounted
        }
        # LEARN: a &= b → keep only items that are in BOTH sets ("intersection")
        self._drives_with_problems &= mounted
