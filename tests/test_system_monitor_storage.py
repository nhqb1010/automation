# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks storage.py (which drives show, slow drives)
#   read next → tests/test_log_viewer_reader.py
import logging

# LEARN: plistlib = read / write Apple's "property list" format (plist)
#   hdiutil (the disk image tool) answers in plist
import plistlib
import threading
import time
from collections.abc import Callable

import pytest

from app.tools.system_monitor import storage
from app.tools.system_monitor.storage import (
    MountedVolume,
    StorageReader,
    VolumeDetails,
    build_drive_usage,
    classify_drive_kind,
    is_user_visible_mountpoint,
    parse_disk_image_mountpoints,
    select_user_visible_volumes,
    sort_drives_for_display,
)


class TestSystemMonitorStorageSelectUserVisibleVolumes:
    def test_system_monitor_storage_select_keeps_main_and_volumes(
        self, fake_mounted_volumes: list[MountedVolume]
    ) -> None:
        selected = select_user_visible_volumes(fake_mounted_volumes)

        assert [volume.mountpoint for volume in selected] == [
            "/",
            "/Volumes/T7",
            "/Volumes/NAS",
            "/Volumes/Installer",
        ]


class TestSystemMonitorStorageIsUserVisibleMountpoint:
    def test_system_monitor_storage_is_user_visible_mountpoint_real_drives(
        self,
    ) -> None:
        assert is_user_visible_mountpoint("/")
        assert is_user_visible_mountpoint("/Volumes/T7")

    def test_system_monitor_storage_is_user_visible_mountpoint_skips_nested(
        self,
    ) -> None:
        assert not is_user_visible_mountpoint("/Volumes/T7/inner")
        assert not is_user_visible_mountpoint("/System/Volumes/Data")

    def test_system_monitor_storage_is_user_visible_mountpoint_skips_system_names(
        self,
    ) -> None:
        assert not is_user_visible_mountpoint(
            "/Volumes/com.apple.TimeMachine.localsnapshots"
        )
        assert not is_user_visible_mountpoint("/Volumes/.timemachine")


class TestSystemMonitorStorageClassifyDriveKind:
    def test_system_monitor_storage_classify_drive_kind_each_kind(self) -> None:
        images = {"/Volumes/Installer"}

        # MountedVolume("/", "apfs") = mountpoint, file system type (by position)
        assert classify_drive_kind(MountedVolume("/", "apfs"), images) == "main"
        assert (
            classify_drive_kind(MountedVolume("/Volumes/NAS", "smbfs"), images)
            == "network"
        )
        assert (
            classify_drive_kind(MountedVolume("/Volumes/Installer", "hfs"), images)
            == "image"
        )
        assert (
            classify_drive_kind(MountedVolume("/Volumes/T7", "exfat"), images)
            == "external"
        )


class TestSystemMonitorStorageBuildDriveUsage:
    def test_system_monitor_storage_build_drive_usage_percent(self) -> None:
        usage = build_drive_usage(
            volume=MountedVolume("/", "apfs"),
            kind="main",
            details=VolumeDetails(
                name="Macintosh HD", total_bytes=500, available_bytes=200
            ),
        )

        assert usage.responding
        assert usage.used_bytes == 300
        assert usage.free_bytes == 200
        assert usage.used_percent == 60.0

    def test_system_monitor_storage_build_drive_usage_not_responding(self) -> None:
        usage = build_drive_usage(
            volume=MountedVolume("/Volumes/NAS", "smbfs"), kind="network", details=None
        )

        assert not usage.responding
        assert usage.name == "NAS"
        assert usage.used_percent is None


class TestSystemMonitorStorageSortDrivesForDisplay:
    def test_system_monitor_storage_sort_main_first_secondary_last(self) -> None:
        drives = [
            build_drive_usage(
                volume=MountedVolume(f"/Volumes/{name}", "x"), kind=kind, details=None
            )
            for name, kind in [("Img", "image"), ("NAS", "network"), ("T7", "external")]
        ]
        drives.append(
            build_drive_usage(
                volume=MountedVolume("/", "apfs"),
                kind="main",
                details=VolumeDetails(
                    name="Macintosh HD", total_bytes=1, available_bytes=1
                ),
            )
        )

        ordered = sort_drives_for_display(drives)

        assert [drive.kind for drive in ordered] == [
            "main",
            "external",
            "network",
            "image",
        ]


class TestSystemMonitorStorageParseDiskImageMountpoints:
    def test_system_monitor_storage_parse_disk_image_mountpoints(self) -> None:
        # build fake hdiutil output: one image mounted, one not
        raw = plistlib.dumps(
            {
                "images": [
                    {
                        "system-entities": [
                            {"dev-entry": "/dev/disk9"},
                            {"mount-point": "/Volumes/Installer"},
                        ]
                    },
                    {"system-entities": []},
                ]
            }
        )

        assert parse_disk_image_mountpoints(raw) == {"/Volumes/Installer"}


def patch_drives_with_hung_shares(
    monkeypatch: pytest.MonkeyPatch, hung_count: int, release: threading.Event
) -> None:
    """
    LEARN: pretend some network shares hang (like an unplugged NAS)

    used by → the StorageReader tests below
    the main disk answers at once; each share waits until "release" is set
    threading.Event = a flag threads can wait on: wait() blocks, set() frees
    """
    hung = [f"/Volumes/NAS{index}" for index in range(hung_count)]

    def read_details_hanging_on_shares(mountpoint: str) -> VolumeDetails:
        if mountpoint in hung:
            release.wait(5)

        return VolumeDetails(name="Macintosh HD", total_bytes=100, available_bytes=50)

    monkeypatch.setattr(
        storage,
        "read_mounted_volumes",
        lambda: [
            MountedVolume("/", "apfs"),
            # *( … ) → spread every item of the generator into this list
            *(MountedVolume(mountpoint, "smbfs") for mountpoint in hung),
        ],
    )
    # set → calling set() gives an empty set → "no disk images"
    monkeypatch.setattr(storage, "read_disk_image_mountpoints", set)
    monkeypatch.setattr(storage, "read_volume_details", read_details_hanging_on_shares)


# run the test's action, then ALWAYS free the hanging threads (finally),
# so no thread is left waiting after the test
def run_with_release(release: threading.Event, action: Callable[[], None]) -> None:
    try:
        action()
    finally:
        release.set()


class TestSystemMonitorStorageReader:
    def test_system_monitor_storage_reader_times_out_hung_drive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        release = threading.Event()
        patch_drives_with_hung_shares(monkeypatch, hung_count=1, release=release)
        drives = []
        # lambda: … → the action as a tiny function; extend → add all drives
        run_with_release(
            release,
            lambda: drives.extend(
                StorageReader(timeout_seconds=0.2).read_storage_stats().drives
            ),
        )

        by_kind = {drive.kind: drive for drive in drives}
        assert by_kind["main"].responding
        assert not by_kind["network"].responding

    def test_system_monitor_storage_reader_many_hung_shares_do_not_block_local(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        release = threading.Event()
        patch_drives_with_hung_shares(monkeypatch, hung_count=5, release=release)
        reader = StorageReader(timeout_seconds=0.3)
        results = []

        def read_storage_twice() -> None:
            results.append(reader.read_storage_stats().drives)
            started = time.monotonic()
            results.append(reader.read_storage_stats().drives)
            results.append(time.monotonic() - started)

        run_with_release(release, read_storage_twice)

        first, second, second_duration = results
        for drives in (first, second):
            by_kind = {drive.kind: drive for drive in drives}
            assert by_kind["main"].responding
        # one shared time limit, not 0.3 s per hung share (which would be 1.5 s)
        assert second_duration < 1.0

    def test_system_monitor_storage_reader_logs_hung_drive_once(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        release = threading.Event()
        patch_drives_with_hung_shares(monkeypatch, hung_count=1, release=release)
        reader = StorageReader(timeout_seconds=0.1)

        def read_storage_three_times() -> None:
            for _ in range(3):
                reader.read_storage_stats()

        with caplog.at_level(logging.WARNING):
            run_with_release(release, read_storage_three_times)

        assert caplog.text.count("Drive problem") == 1
