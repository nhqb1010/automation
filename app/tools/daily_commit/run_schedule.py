# LEARN: YOU ARE HERE
#   [ Runs per day 1-5 ] on the page ▶ DailyCommitTool ▶ THIS FILE works out
#   the times + the cron line ▶ written into the repo's daily.yml ▶ GitHub
#   runs it that many times a day
#   read next → app/preferences.py
"""
How many times a day the workflow runs, and at which times.

LEARN: the rule (you choose 1-5 runs, default 2)
  runs are spread evenly from 08:00 to 20:00 Vietnam time (UTC+7)
  = 01:00 to 13:00 UTC (GitHub's clock is always UTC)

  runs   Vietnam time (UTC+7)              UTC hours in the cron line
  1      08:17                             1
  2      08:17 · 20:17                     1,13
  3      08:17 · 14:17 · 20:17             1,7,13
  4      08:17 · 12:17 · 16:17 · 20:17     1,5,9,13
  5      08:17 · 11:17 · 14:17 · 17:17 · 20:17   1,4,7,10,13

LEARN: why minute 17, not minute 0 (o'clock)
  GitHub's own docs: scheduled runs can be DELAYED when Actions is busy,
  and the busiest moment is the start of every hour (minute 0)
  → so many repos write "0 3 * * *" that runs pile up in a queue at :00
  → if the queue gets long enough, some queued runs are DROPPED (never run)
  any minute away from :00 avoids that pile-up; 17 is simply an
  "odd" minute that few people pick
  it does NOT make GitHub count a commit on your graph more reliably;
  it only makes the run start closer to its time (and not get skipped)
  source: docs.github.com → "Events that trigger workflows" → schedule

LEARN: why more than one run a day
  every run commits → a day gets 2-5 commits instead of 1
  if GitHub fails to count one of them (it happened on 4 Nov 2026,
  during a GitHub outage), the others still turn the day green
"""

import re

RUNS_PER_DAY_MIN = 1
RUNS_PER_DAY_MAX = 5
RUNS_PER_DAY_DEFAULT = 2
# 08:00 and 20:00 in Vietnam (UTC+7) → 01:00 and 13:00 UTC
FIRST_RUN_UTC_HOUR = 1
LAST_RUN_UTC_HOUR = 13
# away from minute 0, GitHub's busiest moment (see the top of this file)
RUN_MINUTE = 17
# a cron line has 5 parts; the last 3 are "*" for a plain daily schedule
CRON_PART_COUNT = 5
DAILY_CRON_TAIL = ["*", "*", "*"]
LAST_MINUTE = 59
LAST_HOUR = 23

# LEARN: regular expression for the ONE schedule line in daily.yml
#     - cron: "17 1,13 * * *"
#   ^ / $ with re.MULTILINE → start / end of ANY line, not just the file
#   ([ \t]*- cron: ")  group 1 = the indent and key (kept as is)
#   ([^"]*)         group 2 = the cron text between the quotes (replaced)
#   (")             group 3 = the closing quote
#   [ \t]* (not \s*) → spaces only; \s would also eat the line break
#   comment lines start with # → "- cron" right after the indent never
#   matches them
CRON_LINE_PATTERN = re.compile(r'^([ \t]*- cron: ")([^"]*)(")[ \t]*$', re.MULTILINE)


def check_runs_per_day(runs_per_day: int) -> int:
    # 1-5 only; anything else → ValueError with a readable reason
    # called by → every function below that takes a count
    if not RUNS_PER_DAY_MIN <= runs_per_day <= RUNS_PER_DAY_MAX:
        raise ValueError(
            f"Runs per day must be {RUNS_PER_DAY_MIN} to {RUNS_PER_DAY_MAX}, "
            f"got {runs_per_day}"
        )

    return runs_per_day


def plan_run_hours_utc(runs_per_day: int) -> list[int]:
    """
    LEARN: N runs → N whole UTC hours, evenly spread over 01:00-13:00

    called by → build_cron_expression, read_runs_per_day_from_workflow
    gives back → e.g. 3 → [1, 7, 13]

    the gap between runs = 12 hours / (N - 1)
      12 splits evenly by 1, 2, 3 and 4 → every count 2-5 gives whole hours
    1 run → only the first time (08:17 Vietnam)
    """
    check_runs_per_day(runs_per_day)
    if runs_per_day == 1:
        return [FIRST_RUN_UTC_HOUR]

    gap = (LAST_RUN_UTC_HOUR - FIRST_RUN_UTC_HOUR) // (runs_per_day - 1)
    return [FIRST_RUN_UTC_HOUR + gap * index for index in range(runs_per_day)]


def build_cron_expression(runs_per_day: int) -> str:
    """
    LEARN: N runs → the cron text GitHub reads

    called by → write_runs_per_day_into_workflow
    gives back → e.g. 2 → "17 1,13 * * *"

    cron = 5 parts: minute  hour  day-of-month  month  weekday
      "17 1,13 * * *" → at minute 17 of hours 1 and 13 (UTC), every day
      a comma list in the hour part → several runs in one line
    """
    hours = ",".join(str(hour) for hour in plan_run_hours_utc(runs_per_day))
    return f"{RUN_MINUTE} {hours} * * *"


def read_cron_expression(workflow_text: str) -> str | None:
    # the cron text inside daily.yml, or None if there is no schedule line
    found = CRON_LINE_PATTERN.search(workflow_text)
    return found.group(2) if found else None


def read_run_times_from_cron(cron: str) -> list[str]:
    """
    LEARN: ANY simple daily cron → its UTC run times, earliest first

    called by → DailyCommitTool (the files step), so the page shows the
      times actually in effect, even for a schedule this app didn't write
      "0 3 * * *"      → ["03:00"]           (the first template's)
      "17 1,13 * * *"  → ["01:17", "13:17"]
    gives back → [] for anything fancier (ranges, steps, weekdays …)

    str.isdigit() → True when the text is only digits ("17" ✓, "*/5" ✗)
    """
    parts = cron.split()
    if len(parts) != CRON_PART_COUNT or parts[2:] != DAILY_CRON_TAIL:
        return []

    minute_text, hours_text = parts[0], parts[1]
    hour_texts = hours_text.split(",")
    if not minute_text.isdigit() or not all(text.isdigit() for text in hour_texts):
        return []

    minute = int(minute_text)
    hours = sorted({int(text) for text in hour_texts})
    if minute > LAST_MINUTE or hours[-1] > LAST_HOUR:
        return []

    return [f"{hour:02d}:{minute:02d}" for hour in hours]


def read_runs_per_day_from_workflow(workflow_text: str) -> int | None:
    """
    LEARN: daily.yml → how many runs a day it is set to (1-5)

    called by → DailyCommitTool (the picker shows it), and
      fit_template_to_repo_schedule (keeps your choice on updates)
    gives back → None when the schedule isn't one this app wrote
      (an older copy like "0 3 * * *", or one edited by hand)

    the cron text is compared with what each count 1-5 would write
    """
    cron = read_cron_expression(workflow_text)
    if cron is None:
        return None

    # LEARN: next(generator, default) → the first match, or the default
    #   same as: for runs in range(1, 6): if … == cron: return runs
    #            return None
    return next(
        (
            runs
            for runs in range(RUNS_PER_DAY_MIN, RUNS_PER_DAY_MAX + 1)
            if build_cron_expression(runs) == cron.strip()
        ),
        None,
    )


def write_runs_per_day_into_workflow(workflow_text: str, runs_per_day: int) -> str:
    """
    LEARN: daily.yml text → the same text with a new schedule line

    called by → DailyCommitTool.set_daily_commit_runs_per_day, and
      fit_template_to_repo_schedule
    only the text between the quotes changes; everything else stays
    no schedule line → ValueError (nothing to change)

    pattern.subn(replacement, text, count=1) → (new text, how many changed)
      \\g<1> / \\g<3> in the replacement → put groups 1 and 3 back
    """
    new_text, count = CRON_LINE_PATTERN.subn(
        rf"\g<1>{build_cron_expression(runs_per_day)}\g<3>", workflow_text, count=1
    )
    if count == 0:
        raise ValueError("daily.yml has no schedule line to change")

    return new_text
