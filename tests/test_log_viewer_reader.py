# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks log_viewer/reader.py with small log files
#   written into tmp_path (a fresh folder per test, never the real logs/)
#   read next → pyproject.toml
from pathlib import Path

import pytest

from app.tools.log_viewer import reader
from app.tools.log_viewer.models import LogCursor
from app.tools.log_viewer.reader import (
    choose_log_read_start,
    parse_log_lines,
    read_new_log_lines,
    take_complete_log_lines,
)


def format_log_line(message: str, level: str = "INFO", source: str = "app.main") -> str:
    # the same layout logging_setup.py writes (level padded to 7 characters)
    return f"2026-10-22 22:12:03 {level:<7} [{source}] {message}\n"


def append_to_log(log_file: Path, text: str) -> None:
    # "a" → append: add to the end, like the app's logger does
    with log_file.open("a", encoding="utf-8") as file:
        file.write(text)


@pytest.fixture
def log_file(tmp_path: Path) -> Path:
    return tmp_path / "app.log"


class TestLogViewerReaderReadNewLogLines:
    def test_log_viewer_reader_read_new_log_lines_first_read_small_file(
        self, log_file: Path
    ) -> None:
        append_to_log(log_file, format_log_line("one") + format_log_line("two"))

        chunk = read_new_log_lines(log_file=log_file, cursor=None, max_lines=100)

        assert [line.message for line in chunk.lines] == ["one", "two"]
        assert chunk.cursor is not None
        assert chunk.cursor.offset == log_file.stat().st_size

    def test_log_viewer_reader_read_new_log_lines_only_new_lines_next_time(
        self, log_file: Path
    ) -> None:
        append_to_log(log_file, format_log_line("old"))
        first = read_new_log_lines(log_file=log_file, cursor=None, max_lines=100)
        append_to_log(log_file, format_log_line("new"))

        second = read_new_log_lines(
            log_file=log_file, cursor=first.cursor, max_lines=100
        )

        assert [line.message for line in second.lines] == ["new"]

    def test_log_viewer_reader_read_new_log_lines_holds_half_written_line(
        self, log_file: Path
    ) -> None:
        # the logger is mid-way through writing the second line
        append_to_log(log_file, format_log_line("done") + "2026-10-22 22:12:04 INF")
        first = read_new_log_lines(log_file=log_file, cursor=None, max_lines=100)
        append_to_log(log_file, "O    [app.main] finished\n")

        second = read_new_log_lines(
            log_file=log_file, cursor=first.cursor, max_lines=100
        )

        assert [line.message for line in first.lines] == ["done"]
        assert [line.message for line in second.lines] == ["finished"]

    def test_log_viewer_reader_read_new_log_lines_rolled_over_starts_at_top(
        self, log_file: Path
    ) -> None:
        append_to_log(log_file, format_log_line("before roll over") * 3)
        first = read_new_log_lines(log_file=log_file, cursor=None, max_lines=100)
        # what the rotating log handler does: rename, then start a new file
        log_file.rename(log_file.with_suffix(".log.1"))
        append_to_log(log_file, format_log_line("fresh file"))

        second = read_new_log_lines(
            log_file=log_file, cursor=first.cursor, max_lines=100
        )

        assert [line.message for line in second.lines] == ["fresh file"]

    def test_log_viewer_reader_read_new_log_lines_missing_file_keeps_cursor(
        self, log_file: Path
    ) -> None:
        cursor = LogCursor(file_id=1, offset=50)

        chunk = read_new_log_lines(log_file=log_file, cursor=cursor, max_lines=100)

        assert not chunk.file_found
        assert chunk.lines == []
        assert chunk.cursor == cursor

    def test_log_viewer_reader_read_new_log_lines_first_read_skips_cut_line(
        self, log_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        append_to_log(log_file, format_log_line("a" * 80) + format_log_line("last"))
        # read only the last 70 bytes → starts inside the first line
        monkeypatch.setattr(reader, "TAIL_BYTES_ON_FIRST_READ", 70)

        chunk = read_new_log_lines(log_file=log_file, cursor=None, max_lines=100)

        assert [line.message for line in chunk.lines] == ["last"]

    def test_log_viewer_reader_read_new_log_lines_keeps_newest_up_to_limit(
        self, log_file: Path
    ) -> None:
        append_to_log(log_file, "".join(format_log_line(f"n{i}") for i in range(5)))

        chunk = read_new_log_lines(log_file=log_file, cursor=None, max_lines=2)

        assert [line.message for line in chunk.lines] == ["n3", "n4"]


class TestLogViewerReaderParseLogLines:
    def test_log_viewer_reader_parse_log_lines_splits_parts(self) -> None:
        (line,) = parse_log_lines(
            [format_log_line("Drive problem", level="WARNING", source="storage")]
        )

        assert line.time == "2026-10-22 22:12:03"
        assert line.level == "WARNING"
        assert line.source == "storage"
        assert line.message == "Drive problem"

    def test_log_viewer_reader_parse_log_lines_traceback_joins_its_line(
        self,
    ) -> None:
        lines = parse_log_lines(
            [
                format_log_line("Tool action failed", level="ERROR"),
                "Traceback (most recent call last):",
                '  File "bridge.py", line 12, in call',
                "ValueError: boom",
            ]
        )

        assert len(lines) == 1
        assert lines[0].extra_lines[-1] == "ValueError: boom"

    def test_log_viewer_reader_parse_log_lines_leading_rest_continues_previous(
        self,
    ) -> None:
        lines = parse_log_lines(["ValueError: boom", format_log_line("next")])

        assert lines[0].continues_previous
        assert lines[0].level == "OTHER"
        assert not lines[1].continues_previous

    def test_log_viewer_reader_parse_log_lines_unknown_level_is_other(self) -> None:
        (line,) = parse_log_lines([format_log_line("odd", level="NOTICE")])

        assert line.level == "OTHER"


class TestLogViewerReaderTakeCompleteLogLines:
    def test_log_viewer_reader_take_complete_log_lines_holds_partial(self) -> None:
        assert take_complete_log_lines(b"a\nb\npart", hit_read_limit=False) == b"a\nb\n"
        assert take_complete_log_lines(b"part", hit_read_limit=False) == b""

    def test_log_viewer_reader_take_complete_log_lines_huge_line_sent_anyway(
        self,
    ) -> None:
        # one line bigger than a whole read → sent, so the cursor still moves
        assert take_complete_log_lines(b"x" * 10, hit_read_limit=True) == b"x" * 10


class TestLogViewerReaderChooseLogReadStart:
    def test_log_viewer_reader_choose_log_read_start_each_case(self) -> None:
        cursor = LogCursor(file_id=7, offset=500)

        assert choose_log_read_start(cursor=cursor, file_id=7, file_size=900) == 500
        # same file but shorter than the bookmark → it was emptied
        assert choose_log_read_start(cursor=cursor, file_id=7, file_size=100) == 0
        # different file → rolled over
        assert choose_log_read_start(cursor=cursor, file_id=8, file_size=900) == 0
        # first read of a large file → only the last part
        assert choose_log_read_start(cursor=None, file_id=7, file_size=1_000_000) == (
            1_000_000 - reader.TAIL_BYTES_ON_FIRST_READ
        )
