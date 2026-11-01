# LEARN: YOU ARE HERE
#   models.py (every LogLine) ▶ THIS FILE: which part of the app wrote it
#   ▶ a name + colour ▶ the coloured tag on each line of the Logs page
#   read next → app/tools/log_viewer/reader.py
"""
Which part of the app a log line came from, and its colour.

LEARN: a log line's source = the logger's name = the Python module
  (each file does logger = logging.getLogger(__name__))

  [app.tools.system_monitor.storage]  → Monitor  blue
  [app.tools.daily_commit.github_client]    → Daily Commit   green
  [app.tools.log_viewer]              → Logs     purple
  [ui]                                → Page     orange   (page JavaScript)
  [app.main], [app.bridge], …         → App      grey
  [app.tools.<new_tool>…]             → its own name, an automatic colour
  [pywebview], anything else          → Other    dim grey

LEARN: why Python decides (not the page)
  one rule, tested once; the page just paints what it's told

LEARN: automatic colours for future tools
  crc32 = a quick checksum: text → a number, always the same for the
    same text → the same tool always gets the same colour
  number % len(palette) → a position in the palette ("%" = remainder)
  industry term: "stable hashing"
"""

import zlib

from pydantic import BaseModel

# a module path inside a tool: app.tools.<tool id>.…
TOOL_SOURCE_PREFIX = "app.tools."


class LogArea(BaseModel):
    """LEARN: one area: id (for the page), label (shown), colour (hex)."""

    id: str
    label: str
    color: str


# LEARN: areas with a fixed colour (source prefix, area)
#   checked before the automatic tool colours and the general "App"
FIXED_LOG_AREAS: tuple[tuple[str, LogArea], ...] = (
    (
        "app.tools.system_monitor",
        LogArea(id="monitor", label="Monitor", color="#3987e5"),
    ),
    (
        "app.tools.daily_commit",
        LogArea(id="daily_commit", label="Daily Commit", color="#2fb36b"),
    ),
    ("app.tools.log_viewer", LogArea(id="logs", label="Logs", color="#9085e9")),
    ("ui", LogArea(id="page", label="Page", color="#d95926")),
)
APP_SOURCE = "app"
# modules in app/tools/ that are shared code, not a tool → "App"
SHARED_TOOL_MODULES = frozenset({"base"})
APP_LOG_AREA = LogArea(id="app", label="App", color="#8a8980")
OTHER_LOG_AREA = LogArea(id="other", label="Other", color="#5f5e57")
# colours for tools without a fixed one (none of them used above)
AUTO_AREA_COLORS = ("#2fb3a6", "#c94f9b", "#d4a72c", "#5aa9e6", "#b07de8", "#e0795b")


def is_source_under(source: str, prefix: str) -> bool:
    # "app.tools.daily_commit.models" is under "app.tools.daily_commit"
    # "app.tools.daily_commits" isn't (another tool)
    return source == prefix or source.startswith(prefix + ".")


def pick_auto_area_color(tool_id: str) -> str:
    """
    LEARN: the same tool id → always the same colour from the palette

    called by → find_log_area, for tools without a fixed colour
    """
    return AUTO_AREA_COLORS[zlib.crc32(tool_id.encode("utf-8")) % len(AUTO_AREA_COLORS)]


def find_log_area(source: str) -> LogArea:
    """
    LEARN: a log line's source → its area

    called by → models.py (LogLine.area), once per line sent to the page
    gives back → LogArea (id, label, colour)

      "app.tools.daily_commit.github_client" → Daily Commit (fixed)
      "app.tools.backup_repos.runner"  → "Backup repos" (automatic colour)
      "app.main"                       → App
      "pywebview" / ""                 → Other
    """
    # 1. a fixed area (Monitor, Daily Commit, Logs, Page)
    for prefix, area in FIXED_LOG_AREAS:
        if is_source_under(source=source, prefix=prefix):
            return area

    # 2. any other tool → its own name + an automatic colour
    #   "app.tools.backup_repos.runner" → "backup_repos"
    if source.startswith(TOOL_SOURCE_PREFIX):
        tool_id = source.removeprefix(TOOL_SOURCE_PREFIX).split(".")[0]
        if tool_id in SHARED_TOOL_MODULES:
            return APP_LOG_AREA

        return LogArea(
            id=tool_id,
            label=tool_id.replace("_", " ").capitalize(),
            color=pick_auto_area_color(tool_id),
        )

    # 3. the rest of the app (app.main, app.bridge, app.tools, …) → App
    if is_source_under(source=source, prefix=APP_SOURCE):
        return APP_LOG_AREA

    # 4. libraries (pywebview, …) and lines without a source
    return OTHER_LOG_AREA
