# LEARN: YOU ARE HERE
#   [ Set up / update repo ] ▶ DailyCommitTool reads the repo's copies
#   ▶ THIS FILE compares them with repo_template/ ▶ a plan with diffs
#   ▶ shown to you first; only [ Apply ] commits it
#   read next → app/tools/daily_commit/run_schedule.py
"""
Compare the repo template with the notes repo, and plan the update.

LEARN: set up and update are the same thing
  empty repo  → every file is "new"     → one commit adds them all
  older copy  → some files "changed"    → one commit updates those
  up to date  → nothing to do

    repo_template/ (this app)        notes repo (GitHub)
    daily.yml  ───── compare ─────▶  daily.yml   → same / changed / new
    daily.py   ───── compare ─────▶  daily.py    → same / changed / new
    content.txt ──── only if missing ▶ content.txt → new / kept

  content.txt is YOURS once it exists → never overwritten ("kept")

LEARN: your runs-per-day choice is kept too
  the template's daily.yml says 2 runs a day; yours may say 4
  → before comparing, the template copy gets YOUR count written in
  → a different count alone never shows as "Update available"
"""

import difflib
import importlib.util
from datetime import date, datetime, timedelta
from functools import cache
from pathlib import Path
from types import ModuleType

from app.tools.daily_commit.models import (
    TemplateFileChange,
    NextPost,
    TemplateFileState,
    TemplateSyncPlan,
)
from app.tools.daily_commit.run_schedule import (
    read_runs_per_day_from_workflow,
    write_runs_per_day_into_workflow,
)

TEMPLATE_DIR = Path(__file__).parent / "repo_template"
# repo paths, in the order shown on the page
TEMPLATE_PATHS = (".github/workflows/daily.yml", "daily.py", "content.txt")
# created once by set up, then edited by you → never replaced
USER_OWNED_PATHS = frozenset({"content.txt"})
# the workflow's file name, as GitHub's Actions API knows it
WORKFLOW_FILE_NAME = "daily.yml"
WORKFLOW_PATH = ".github/workflows/daily.yml"
CONTENT_PATH = "content.txt"


def read_template_files(template_dir: Path = TEMPLATE_DIR) -> dict[str, str]:
    """
    LEARN: repo path → file text, for every template file

    called by → DailyCommitTool, for set up / update and the files card
    dict comprehension { key: value for … } ≈ a for-loop filling a dict
    """
    return {
        path: (template_dir / path).read_text(encoding="utf-8")
        for path in TEMPLATE_PATHS
    }


def fit_template_to_repo_schedule(
    template_files: dict[str, str], repo_files: dict[str, str | None]
) -> dict[str, str]:
    """
    LEARN: the template files, with the repo's runs-per-day kept

    called by → DailyCommitTool, before every plan_template_sync
    the repo's daily.yml says N runs (1-5) → the template's copy says N too
    no daily.yml yet, or a schedule this app didn't write → template as is
      (an update then brings the default, 2 runs a day)
    gives back → a NEW dict; the one passed in isn't changed
    """
    repo_workflow = repo_files.get(WORKFLOW_PATH)
    if repo_workflow is None or WORKFLOW_PATH not in template_files:
        return dict(template_files)

    runs_per_day = read_runs_per_day_from_workflow(repo_workflow)
    if runs_per_day is None:
        return dict(template_files)

    # LEARN: {**a, key: value} → a copy of a with one entry replaced
    return {
        **template_files,
        WORKFLOW_PATH: write_runs_per_day_into_workflow(
            workflow_text=template_files[WORKFLOW_PATH], runs_per_day=runs_per_day
        ),
    }


def compare_template_file(
    path: str, template_text: str, repo_text: str | None
) -> TemplateFileChange:
    """
    LEARN: one file: template vs the repo's copy → status + diff

    called by → plan_template_sync, once per template file
    repo_text None → the repo doesn't have it yet

    difflib.unified_diff → the "- old / + new" lines, like git diff
      splitlines(keepends=True) → lines that keep their "\n"
      fromfile / tofile → the two names shown at the top of the diff
    """
    if repo_text is None:
        diff = difflib.unified_diff(
            [],
            template_text.splitlines(keepends=True),
            fromfile="/dev/null",
            tofile=path,
        )
        return TemplateFileChange(path=path, status="new", diff="".join(diff))

    if path in USER_OWNED_PATHS:
        return TemplateFileChange(path=path, status="kept", diff="")

    if repo_text == template_text:
        return TemplateFileChange(path=path, status="same", diff="")

    diff = difflib.unified_diff(
        repo_text.splitlines(keepends=True),
        template_text.splitlines(keepends=True),
        fromfile=f"repo: {path}",
        tofile=f"template: {path}",
    )
    return TemplateFileChange(path=path, status="changed", diff="".join(diff))


def plan_template_sync(
    template_files: dict[str, str], repo_files: dict[str, str | None]
) -> TemplateSyncPlan:
    """
    LEARN: all template files compared → the plan the page shows

    called by → DailyCommitTool.preview_template_sync and apply_template_sync
    repo_files → path → the repo's text (None = missing)
    """
    changes = [
        compare_template_file(
            path=path, template_text=text, repo_text=repo_files.get(path)
        )
        for path, text in template_files.items()
    ]
    up_to_date = all(change.status in {"same", "kept"} for change in changes)
    return TemplateSyncPlan(changes=changes, up_to_date=up_to_date)


def list_template_file_states(plan: TemplateSyncPlan) -> list[TemplateFileState]:
    # the files card only needs path + status (no diffs)
    # called by → DailyCommitTool overview
    return [
        TemplateFileState(path=change.path, status=change.status)
        for change in plan.changes
    ]


def pick_files_to_commit(
    plan: TemplateSyncPlan, template_files: dict[str, str]
) -> dict[str, str]:
    """
    LEARN: only the "new" and "changed" files go into the commit

    called by → DailyCommitTool.apply_template_sync
    """
    return {
        change.path: template_files[change.path]
        for change in plan.changes
        if change.status in {"new", "changed"}
    }


@cache
def load_daily_script() -> ModuleType:
    """
    LEARN: daily.py (the script GitHub runs), loaded as a module

    called by → preview_next_post, to use the SAME picker GitHub uses
    repo_template/ isn't a Python package → loaded straight from its file
      spec_from_file_location → "a module lives in this file"
      exec_module → run it once (defines its functions; main() doesn't run)
    @cache → loaded the first time only, then the same module every time
    """
    spec = importlib.util.spec_from_file_location(
        "daily_commit_daily_script", TEMPLATE_DIR / "daily.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("daily.py could not be loaded")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preview_next_post(content_text: str, now: datetime, today_posted: bool) -> NextPost:
    """
    LEARN: which line (and emoji) the next post will get

    called by → DailyCommitTool overview ▶ the "Today's line" card
    today not posted yet → today's pick; already posted → tomorrow's
    the pick is seeded by the date (see daily.py) → the same answer here
      and on GitHub's runner
    """
    daily = load_daily_script()
    day = now + timedelta(days=1) if today_posted else now
    lines = daily.read_content_lines(content_text)
    return NextPost(
        day=date(day.year, day.month, day.day),
        line=daily.pick_line_for_day(lines, day),
        emoji=daily.pick_emoji_for_day(day),
        is_today=not today_posted,
        line_count=len(lines),
    )
