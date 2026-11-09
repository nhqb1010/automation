# LEARN: YOU ARE HERE
#   DailyCommitTool hands in what GitHub said (file names, runs) ▶ THIS FILE
#   works out streak, calendar and minutes ▶ models ▶ the Daily Commit page
#   read next → app/tools/daily_commit/template_sync.py
"""
Streak, calendar and Actions-minutes numbers, from plain data.

LEARN: no GitHub calls in here, only arithmetic on what was fetched
  → every function is easy to test with made-up inputs
  industry term: "pure functions" (same input → same output, no side effects)

LEARN: which days count
  a day counts when the notes repo has its file: days/2026/11-03.md
  days are UTC days, the same clock GitHub's contribution graph uses
"""

import math
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.tools.daily_commit.models import (
    CalendarDay,
    MinutesLevel,
    MinutesUsage,
    WorkflowRun,
)

DAYS_PER_WEEK = 7
CALENDAR_WEEKS = 12
# GitHub Free: about 2,000 Actions minutes a month for private repos
PRIVATE_MINUTES_PER_MONTH = 2000
WARNING_PERCENT = 75
CRITICAL_PERCENT = 90
# "11-03.md" → month 11, day 03
POST_FILE_PATTERN = re.compile(r"^(\d{2})-(\d{2})\.md$")
YEAR_FOLDER_PATTERN = re.compile(r"^\d{4}$")


def read_posted_days(names_by_year: dict[str, list[str]]) -> set[date]:
    """
    LEARN: folder listings → the set of days that have a post

    called by → DailyCommitTool overview
    names_by_year → {"2026": ["11-02.md", "11-03.md"], …}
    gives back → {date(2026, 11, 2), date(2026, 11, 3)}
    anything else in the folders (README, odd names, bad dates) is ignored

    set = a collection with no duplicates and a fast "x in s" check
    """
    posted: set[date] = set()
    for year, names in names_by_year.items():
        if not YEAR_FOLDER_PATTERN.match(year):
            continue

        for name in names:
            # LEARN: walrus := → assign AND test in one go
            #   same as: found = POST_FILE_PATTERN.match(name); if found: …
            if found := POST_FILE_PATTERN.match(name):
                try:
                    posted.add(
                        date(int(year), int(found.group(1)), int(found.group(2)))
                    )
                except ValueError:
                    # e.g. 02-30.md → no such day
                    continue

    return posted


def count_current_streak(posted: set[date], today: date) -> int:
    """
    LEARN: how many days in a row, ending today

    called by → DailyCommitTool overview
    today not posted YET → the streak still counts up to yesterday
      (the day isn't over; today's runs may simply not have happened yet)

      posted: … ✓ ✓ ✓ ✓ [today ✗]  → 4
      posted: … ✓ ✗ ✓ ✓ [today ✓]  → 3
    """
    day = today if today in posted else today - timedelta(days=1)
    streak = 0
    while day in posted:
        streak += 1
        day -= timedelta(days=1)

    return streak


def count_longest_streak(posted: set[date]) -> int:
    """
    LEARN: the most days in a row, ever (the "Best streak" tile)

    called by → DailyCommitTool overview
    walk the days oldest → newest; a day right after the previous one
    makes the run longer, anything else starts a new run

      ✓ ✓ ✗ ✓ ✓ ✓ ✗ ✓  → 3
    sorted(set) → a list, oldest first
    """
    longest = 0
    run = 0
    previous: date | None = None
    for day in sorted(posted):
        run = run + 1 if previous and day - previous == timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day

    return longest


def build_streak_calendar(
    posted: set[date], today: date, weeks: int = CALENDAR_WEEKS
) -> list[CalendarDay]:
    """
    LEARN: the last 12 weeks, one square per day, Monday first

    called by → DailyCommitTool overview
    gives back → weeks × 7 days, oldest first; the page draws them as
      columns (one column = one week), like GitHub's own graph

        week →  1  2  3 … 12
        Mon     ■  ■  □    ■
        Tue     ■  □  ■    ■ ← today
        …                  ·  (rest of this week: is_future)

    today.weekday() → 0 Monday … 6 Sunday
    """
    this_monday = today - timedelta(days=today.weekday())
    first_day = this_monday - timedelta(weeks=weeks - 1)
    days = [
        first_day + timedelta(days=offset) for offset in range(weeks * DAYS_PER_WEEK)
    ]
    return [
        CalendarDay(day=day, posted=day in posted, is_future=day > today)
        for day in days
    ]


def read_github_time(text: str | None) -> datetime | None:
    # "2026-11-03T03:00:12Z" → a datetime in UTC (None stays None)
    if not text:
        return None

    return datetime.fromisoformat(text)


def summarize_workflow_run(raw: dict[str, Any]) -> WorkflowRun:
    """
    LEARN: one run as GitHub describes it (dozens of fields) → the few we show

    called by → DailyCommitTool overview, for the recent-runs list
    duration → from "started" to "last updated"; only for finished runs
    """
    started = read_github_time(raw.get("run_started_at"))
    updated = read_github_time(raw.get("updated_at"))
    duration = None
    if raw.get("status") == "completed" and started and updated:
        duration = max(0, int((updated - started).total_seconds()))

    return WorkflowRun(
        status=raw.get("status", "unknown"),
        conclusion=raw.get("conclusion"),
        event=raw.get("event", "unknown"),
        created_at=read_github_time(raw.get("created_at")) or datetime.now(UTC),
        duration_seconds=duration,
        html_url=raw.get("html_url", ""),
    )


def classify_minutes_level(percent: float) -> MinutesLevel:
    """called by → estimate_actions_minutes ▶ the minutes bar's colour."""
    if percent >= CRITICAL_PERCENT:
        return "critical"
    if percent >= WARNING_PERCENT:
        return "warning"

    return "ok"


def estimate_actions_minutes(
    runs: list[WorkflowRun], now: datetime, is_private: bool
) -> MinutesUsage:
    """
    LEARN: Actions minutes used this month, estimated from run durations

    called by → DailyCommitTool overview
    each finished run → rounded UP to whole minutes (how GitHub bills)
      math.ceil(15 / 60) → 1     math.ceil(61 / 60) → 2
    a run without a duration (still going) → not counted yet
    public repo → free: the number is still shown, with no limit

    why "estimate": GitHub's exact bill also counts other repos' private
    workflows; this counts only the notes repo
    """
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month = [
        run
        for run in runs
        if run.created_at >= month_start and run.duration_seconds is not None
    ]
    used = sum(math.ceil(max(run.duration_seconds or 0, 1) / 60) for run in this_month)
    if not is_private:
        return MinutesUsage(
            used_minutes=used,
            limit_minutes=None,
            percent=0.0,
            level="free",
            run_count=len(this_month),
        )

    percent = round(100 * used / PRIVATE_MINUTES_PER_MONTH, 1)
    return MinutesUsage(
        used_minutes=used,
        limit_minutes=PRIVATE_MINUTES_PER_MONTH,
        percent=percent,
        level=classify_minutes_level(percent),
        run_count=len(this_month),
    )
