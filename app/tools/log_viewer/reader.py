# LEARN: YOU ARE HERE
#   Logs page polls ▶ bridge ▶ log_viewer/__init__.py ▶ THIS FILE reads
#   only the new part of logs/app.log ▶ LogChunk ▶ JSON ▶ page
#   read next → app/preferences.py
"""
Reads new lines from the app's log file, a little at a time.

LEARN: how "follow the log" works (like tail -f in the terminal)

  app.log  [██████████████████████████░░░░░]
            └── already sent ──────────┘└new┘
                                       ▲
                                  cursor.offset

  1st call  → no cursor → send only the last part of the file
  next call → start at the cursor, read to the end, move the cursor
  log rolls over (1 MB) → new file id → start at the new file's top

  industry term: "tailing" a log
"""

import re
from pathlib import Path

from app.tools.log_viewer.models import LogChunk, LogCursor, LogLevel, LogLine

# the first read shows only the end of the file (≈ the last few thousand lines)
TAIL_BYTES_ON_FIRST_READ = 256_000
# one call never reads more than this → a huge burst can't freeze anything
MAX_BYTES_PER_READ = 1_000_000
# level name in the file → the level the page knows; anything else → "OTHER"
LOG_LEVEL_BY_NAME: dict[str, LogLevel] = {
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "WARNING": "WARNING",
    "ERROR": "ERROR",
    "CRITICAL": "CRITICAL",
}

# LEARN: regular expression (regex) = a pattern that text must match
#   matches lines written by app/logging_setup.py, e.g.
#   2026-10-22 22:12:03 WARNING [app.tools.storage] Drive problem …
#
#   ^ … $              → the whole line, start to end
#   \d{4}              → exactly 4 digits
#   (?P<time> … )      → a named group: match["time"] gives that part
#   [A-Z]+             → one or more capital letters (the level)
#   \s+                → one or more spaces (levels are padded to 7)
#   \[ … \]            → literal square brackets
#   [^\]]+             → any characters except ]
#   .*                 → anything (the rest of the line)
#   r"…" = a "raw" string: backslashes are kept as typed
LOG_LINE_PATTERN = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>[A-Z]+)\s+"
    r"\[(?P<source>[^\]]+)\] "
    r"(?P<message>.*)$"
)


def read_new_log_lines(
    log_file: Path, cursor: LogCursor | None, max_lines: int
) -> LogChunk:
    """
    LEARN: everything added to the log since the cursor

    called by → LogViewerTool.read_new_log_lines, on every poll
    gives back → LogChunk (new lines + the cursor for next time)

    steps
      1. where to start: last part (1st call), cursor, or top (new file)
      2. read at most 1 MB from there
      3. keep only complete lines; a half-written last line waits
      4. split each line into time / level / source / message
    """
    try:
        # stat() → facts about the file: size, inode number, …
        file_stats = log_file.stat()
    except FileNotFoundError:
        # no log yet → keep the old bookmark; a new file is noticed later
        return LogChunk(lines=[], cursor=cursor, file_found=False)

    file_id = file_stats.st_ino
    file_size = file_stats.st_size
    is_first_read = cursor is None
    start = choose_log_read_start(cursor=cursor, file_id=file_id, file_size=file_size)
    end = min(file_size, start + MAX_BYTES_PER_READ)

    # LEARN: "rb" = read bytes (not text)
    #   byte offsets stay exact; text decoding comes after
    #   seek(n) → jump to byte n; read(k) → the next k bytes
    with log_file.open("rb") as file:
        file.seek(start)
        data = file.read(end - start)

    # 1st read started in the middle of the file → its first line is cut
    # off → drop everything up to the first line break
    skipped = 0
    if is_first_read and start > 0:
        first_break = data.find(b"\n")
        skipped = first_break + 1 if first_break >= 0 else len(data)
        data = data[skipped:]

    complete = take_complete_log_lines(
        data=data, hit_read_limit=end - start == MAX_BYTES_PER_READ
    )
    # LEARN: errors="replace" → a broken character becomes � instead of a crash
    text = complete.decode("utf-8", errors="replace")
    lines = parse_log_lines(text.splitlines())

    return LogChunk(
        # [-max_lines:] → only the newest max_lines entries
        lines=lines[-max_lines:],
        cursor=LogCursor(file_id=file_id, offset=start + skipped + len(complete)),
        file_found=True,
    )


def choose_log_read_start(
    cursor: LogCursor | None, file_id: int, file_size: int
) -> int:
    """
    LEARN: the byte to start reading from

    called by → read_new_log_lines

      no cursor (page just opened)  → near the end (the last ~256 KB)
      different file id (rolled)    → 0, the top of the new file
      file shorter than the cursor  → 0 (it was emptied / replaced)
      otherwise                     → the cursor, where we stopped last time
    """
    if cursor is None:
        return max(0, file_size - TAIL_BYTES_ON_FIRST_READ)
    if cursor.file_id != file_id or file_size < cursor.offset:
        return 0

    return cursor.offset


def take_complete_log_lines(data: bytes, hit_read_limit: bool) -> bytes:
    """
    LEARN: keep only whole lines (up to and including the last line break)

    called by → read_new_log_lines
    gives back → the bytes that end with a line break

    the app may be in the middle of writing a line right now
      "…done\\nStarting refre" → keep "…done\\n", "Starting refre" waits
      the cursor stops before it → the next poll reads the whole line

    one line longer than the whole 1 MB read → send it anyway
      (else the cursor would never move: industry term "stuck reader")
    """
    last_break = data.rfind(b"\n")
    if last_break < 0:
        return data if hit_read_limit else b""

    # data[:n] → the first n bytes
    return data[: last_break + 1]


def parse_log_lines(raw_lines: list[str]) -> list[LogLine]:
    """
    LEARN: split lines into parts, and attach tracebacks to their line

    called by → read_new_log_lines
    gives back → one LogLine per log entry

      22:12:09 ERROR [ui] Tool action failed     ← matches → new entry
      Traceback (most recent call last):          ← no match → extra line
        File "…", line 12, in call               ← extra line
      ValueError: boom                            ← extra line
    """
    entries: list[LogLine] = []
    for raw in raw_lines:
        if not raw.strip():
            continue

        # LEARN: pattern.match(text) → a Match object, or None if it doesn't fit
        match = LOG_LINE_PATTERN.match(raw)
        if match:
            entries.append(
                LogLine(
                    time=match["time"],
                    level=normalize_log_level(match["level"]),
                    source=match["source"],
                    message=match["message"],
                    extra_lines=[],
                    continues_previous=False,
                )
            )
            continue

        # belongs to the entry above it
        if entries:
            entries[-1].extra_lines.append(raw)
            continue

        # first line of this batch and no entry above it → the rest of the
        # last entry the page already has
        entries.append(
            LogLine(
                time="",
                level="OTHER",
                source="",
                message=raw,
                extra_lines=[],
                continues_previous=True,
            )
        )

    return entries


def normalize_log_level(level: str) -> LogLevel:
    # anything unexpected → "OTHER" (shown, but in the plain style)
    # .get(key, default) → the value, or the default when the key is missing
    return LOG_LEVEL_BY_NAME.get(level, "OTHER")
