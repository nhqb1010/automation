# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks app/build_info.py (the version stamp)
#   read next → tests/test_app_state.py
from pathlib import Path

from app.build_info import (
    BuildInfo,
    format_build_label,
    load_build_info,
    read_project_version,
    write_build_info_file,
)


class TestAppBuildInfoFormatBuildLabel:
    def test_app_build_info_format_build_label_installed(self) -> None:
        info = BuildInfo(
            version="0.1.0",
            built_at="2026-10-29T22:40:00",
            commit="ff822d1",
            is_dev=False,
        )

        assert (
            format_build_label(info) == "Version 0.1.0 · built 29 Oct 22:40 · ff822d1"
        )

    def test_app_build_info_format_build_label_dev_without_commit(self) -> None:
        info = BuildInfo(version="0.1.0", built_at=None, commit=None, is_dev=True)

        assert format_build_label(info) == "Version 0.1.0 · dev"


class TestAppBuildInfoLoadBuildInfo:
    def test_app_build_info_load_build_info_installed_reads_file(
        self, tmp_path: Path
    ) -> None:
        stamp_file = tmp_path / "build_info.json"
        stamp_file.write_text(
            '{"version": "0.2.0", "built_at": null, "commit": "abc", "is_dev": false}'
        )

        info = load_build_info(is_installed=True, build_info_file=stamp_file)

        assert (info.version, info.commit) == ("0.2.0", "abc")

    def test_app_build_info_load_build_info_installed_missing_file(
        self, tmp_path: Path
    ) -> None:
        info = load_build_info(
            is_installed=True, build_info_file=tmp_path / "missing.json"
        )

        assert info.version == "unknown"

    def test_app_build_info_load_build_info_dev_marks_dev(self) -> None:
        info = load_build_info(is_installed=False)

        assert info.is_dev
        assert info.built_at is None


class TestAppBuildInfoReadProjectVersion:
    def test_app_build_info_read_project_version(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "x"\nversion = "3.4.5"\n')

        assert read_project_version(pyproject) == "3.4.5"


class TestAppBuildInfoWriteBuildInfoFile:
    def test_app_build_info_write_build_info_file_round_trip(
        self, tmp_path: Path
    ) -> None:
        stamp_file = tmp_path / "nested" / "build_info.json"

        write_build_info_file(stamp_file)
        info = load_build_info(is_installed=True, build_info_file=stamp_file)

        assert not info.is_dev
        assert info.built_at is not None
