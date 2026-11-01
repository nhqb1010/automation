# LEARN: YOU ARE HERE
#   daily_commit/__init__.py fills these shapes ▶ bridge turns them into JSON
#   ▶ the Daily Commit page reads the same field names
#   read next → app/tools/daily_commit/github_client.py
"""
Data shapes the Daily Commit tool sends to its page.

LEARN: the page loads in four parts (each one a step on the loading screen)

  RepoSection      connection, repo (private? link? empty?), problem
  PostsSection     today posted? streaks, the 12-week calendar
  WorkflowSection  active / paused / missing, recent runs, minutes
  FilesSection     is each template file up to date? the next post's line

  the page asks for them on open, on [ Refresh ], and after every action
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

# LEARN: Literal[...] = only these exact values are allowed
#   "dev_env"  → the dev copy, from .env
#   "keychain" → the installed app, from the macOS Keychain
#   "none"     → not connected yet
type ConnectionSource = Literal["dev_env", "keychain", "none"]
# "missing" → daily.yml isn't in the repo yet (set up not done)
type WorkflowState = Literal["active", "paused", "missing"]
# per template file: compared with what's in the repo
#   "new"     → not in the repo yet
#   "changed" → in the repo, but different from the template
#   "same"    → identical
#   "kept"    → content.txt exists → it's yours, never overwritten
type TemplateFileStatus = Literal["new", "changed", "same", "kept"]
# minutes bar colour: ok < 75 % ≤ warning < 90 % ≤ critical
type MinutesLevel = Literal["free", "ok", "warning", "critical"]


class ConnectionInfo(BaseModel):
    """
    LEARN: where the GitHub connection comes from (never the token itself)

    can_edit → True only in the installed app (Keychain); the dev copy's
      connection is whatever .env says
    """

    source: ConnectionSource
    repository: str | None
    can_edit: bool


class RepoInfo(BaseModel):
    """The notes repo, as GitHub describes it."""

    full_name: str
    private: bool
    html_url: str
    default_branch: str
    # False → the repo has no commits yet (set up creates the first one)
    has_commits: bool


class CalendarDay(BaseModel):
    """
    LEARN: one square of the 12-week calendar

    is_future → the rest of this week (drawn empty, like GitHub's graph)
    """

    day: date
    posted: bool
    is_future: bool


class WorkflowRun(BaseModel):
    """
    LEARN: one run of daily.yml, for the "recent runs" list

    status     → "queued", "in_progress", "completed"
    conclusion → when completed: "success", "failure", "cancelled", …
    event      → "schedule" (the daily timer) or "workflow_dispatch" (by hand)
    """

    status: str
    conclusion: str | None
    event: str
    created_at: datetime
    duration_seconds: int | None
    html_url: str


class WorkflowInfo(BaseModel):
    state: WorkflowState
    html_url: str | None
    recent_runs: list[WorkflowRun]


class MinutesUsage(BaseModel):
    """
    LEARN: GitHub Actions minutes used this month (an ESTIMATE)

    GitHub bills each run rounded UP to a whole minute
      → 15 s run = 1 minute
    public repo → free → limit None, level "free"
    private repo on GitHub Free → about 2,000 minutes a month
    """

    used_minutes: int
    limit_minutes: int | None
    percent: float
    level: MinutesLevel
    run_count: int


class TemplateFileState(BaseModel):
    path: str
    status: TemplateFileStatus


class NextPost(BaseModel):
    """
    LEARN: the line the NEXT post will use (the "Today's line" card)

    is_today → True: today's post isn't in yet, this is today's line
               False: today is done, this is tomorrow's line
    worked out with daily.py's own picker → always what GitHub posts
      (unless you post your own message instead)
    """

    day: date
    line: str
    emoji: str
    is_today: bool
    # how many lines content.txt offers to pick from
    line_count: int


class RepoSection(BaseModel):
    """
    LEARN: loading step 1: the connection and the repo

    repo None → not connected, or unreachable (problem says why)
    today → the UTC date, so the page can explain whose day it is
    """

    connection: ConnectionInfo
    repo: RepoInfo | None
    problem: str | None
    today: date


class PostsSection(BaseModel):
    """LEARN: loading step 2: posts → today, streaks, calendar."""

    today_posted: bool
    current_streak: int
    longest_streak: int
    total_posts: int
    calendar: list[CalendarDay]


class WorkflowSection(BaseModel):
    """LEARN: loading step 3: the workflow, its runs, Actions minutes."""

    workflow: WorkflowInfo
    minutes: MinutesUsage


class FilesSection(BaseModel):
    """LEARN: loading step 4: template files + the next post's line."""

    files: list[TemplateFileState]
    next_post: NextPost


class TemplateFileChange(BaseModel):
    """
    LEARN: one file in an update preview

    diff → the change in "unified diff" format (industry term):
      lines starting with - are removed, + are added
      empty when the file is "same" or "kept"
    """

    path: str
    status: TemplateFileStatus
    diff: str


class TemplateSyncPlan(BaseModel):
    """What [ Set up / update repo ] would change, shown before applying."""

    changes: list[TemplateFileChange]
    # True → nothing to do
    up_to_date: bool


class TemplateSyncResult(BaseModel):
    committed_paths: list[str]
    commit_url: str | None


class ContentFile(BaseModel):
    """
    LEARN: content.txt, for the editor

    sha = GitHub's fingerprint of the file's current version
      sent back on save → GitHub refuses the save if the file changed
      in between (someone edited it on GitHub meanwhile)
      industry term: "optimistic concurrency" / "compare-and-swap"
    """

    text: str
    sha: str | None


class ActionResult(BaseModel):
    """A short "done" answer for buttons like Run now and Pause."""

    message: str


class ConnectionReport(BaseModel):
    """
    LEARN: the answer to [ Test connection ]

    checks → one line per check, e.g. ("Repository found", True)
    """

    ok: bool
    checks: list[tuple[str, bool]]
