# LEARN: YOU ARE HERE
#   reader.py fills these shapes ▶ bridge turns them into JSON
#   ▶ the Logs page reads the same field names
#   read next → app/tools/log_viewer/reader.py
"""
Data shapes the Logs tool sends to its page.

LEARN: one call from the page gives back one LogChunk

  LogChunk ─┬─ lines: [LogLine, …]     the new lines since last time
            ├─ cursor: LogCursor       "where to continue next time"
            └─ file_found              False → no log file yet

  the page keeps the cursor and sends it back with its next call
    → Python remembers nothing between calls
    industry term: "stateless" (cursor = a "continuation token")
"""

from typing import Literal

from pydantic import BaseModel

# LEARN: "OTHER" = a line that doesn't look like our log format
#   (e.g. a traceback with no line above it to attach to)
type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "OTHER"]


class LogLine(BaseModel):
    """
    LEARN: one log line, split into its parts

    2026-10-22 22:12:03 WARNING [app.tools.storage] Drive problem …
    └──── time ───────┘ └level┘ └──── source ─────┘ └─ message ─┘

    extra_lines → lines that belong to this one (an error's traceback)
    continues_previous → True when the first lines of a batch are the rest
      of an entry sent in the LAST batch → the page joins them to it
    """

    time: str
    level: LogLevel
    source: str
    message: str
    extra_lines: list[str]
    continues_previous: bool


class LogCursor(BaseModel):
    """
    LEARN: a bookmark in the log file

    file_id = the file's "inode" number (macOS's id for one file)
      the log rolls over → a NEW app.log gets a new id → start from its top
    offset = how many bytes were already read
    """

    file_id: int
    offset: int


class LogChunk(BaseModel):
    """LEARN: one answer to the page: new lines + the bookmark to send back."""

    lines: list[LogLine]
    # None → nothing read yet (no log file so far)
    cursor: LogCursor | None
    file_found: bool
