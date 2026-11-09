# LEARN: YOU ARE HERE
#   daily.yml step "Write today's post" ▶ THIS FILE runs on GitHub's runner
#   ▶ writes days/YYYY/MM-DD.md ▶ the next step commits it as you
#   read next → app/tools/daily_commit/repo_template/content.txt
"""
Writes today's post from a random line of content.txt.

LEARN: this script only WRITES a file; committing is the workflow's job
  → it never touches git or the internet
  → it's easy to test, and easy to try on your own Mac:
      python3 daily.py      (then look in the days/ folder)

LEARN: it runs on GitHub's computer, not your Mac
  that computer has Python 3.12 → nothing newer than 3.12 is used here
  and nothing outside Python's standard library (nothing to install)

LEARN: what a post looks like

  days/2026/11-03.md
  ──────────────────────────────────────────
  # Tue 3 Nov 2026 🌱

  > Honey never spoils 🍯

  a later run on the same day (the 2nd-5th scheduled run, or
  [ Run now ]) adds below, with a different line:

  ---
  **10:42 UTC** · Shipped the new settings page
"""

import os
import random
from datetime import UTC, datetime
from pathlib import Path

# LEARN: Path(__file__).parent = the folder this script is in = the repo
REPO_DIR = Path(__file__).parent
CONTENT_FILE = REPO_DIR / "content.txt"
DAYS_DIR = REPO_DIR / "days"
# set by daily.yml when you used [ Run now with a message ]
MESSAGE_VARIABLE = "DAILY_MESSAGE"
FALLBACK_LINE = "Showed up today ✓"
EMOJIS = ["🌱", "🔥", "⚡", "🚀", "🎯", "☕", "🌊", "🍀", "✨", "🧠", "🎧", "🏃"]


def read_content_lines(text: str) -> list[str]:
    """
    LEARN: the usable lines of content.txt

    called by → main
    gives back → every line that isn't empty and isn't a # comment

      "# my list"   → skipped (a comment, for you)
      ""            → skipped
      "Honey never spoils 🍯" → kept
    """
    # LEARN: list comprehension with a condition
    #   same as:
    #     lines = []
    #     for line in text.splitlines():
    #         line = line.strip()
    #         if line and not line.startswith("#"):
    #             lines.append(line)
    stripped = [line.strip() for line in text.splitlines()]
    return [line for line in stripped if line and not line.startswith("#")]


def pick_line_for_day(lines: list[str], day: datetime) -> str:
    """
    LEARN: choose one line for this day

    called by → main
    the same day always gets the same line (a second run that day matches)
    → random.Random(seed) = a random picker that always gives the same
      choices for the same seed; the seed here is the date (e.g. 20261103)
    industry term: "seeded" / "deterministic" randomness
    """
    if not lines:
        return FALLBACK_LINE

    seed = int(day.strftime("%Y%m%d"))
    return random.Random(seed).choice(lines)


def pick_line_for_extra_run(lines: list[str], day: datetime) -> str:
    """
    LEARN: the line for a 2nd, 3rd … run on the same day

    called by → main, when today's file already exists
    several runs a day (see daily.yml) → each extra entry gets its own line
    seed = date + hour + minute (e.g. 202611031317) → each run time picks
      differently, but the same run time always picks the same line
    the day's first line is left out (when there's more than one line)
      → an extra entry never repeats the title line
    """
    first_line = pick_line_for_day(lines, day)
    others = [line for line in lines if line != first_line] or lines
    if not others:
        return FALLBACK_LINE

    seed = int(day.strftime("%Y%m%d%H%M"))
    return random.Random(seed).choice(others)


def pick_emoji_for_day(day: datetime) -> str:
    # same idea as pick_line_for_day: one fixed emoji per date
    # (seed + 1 → a different random pick than the line's)
    # called by → main; the emoji goes into the day's title
    seed = int(day.strftime("%Y%m%d")) + 1
    return random.Random(seed).choice(EMOJIS)


def find_post_path(days_dir: Path, day: datetime) -> Path:
    # 3 Nov 2026 → days/2026/11-03.md  (one folder per year keeps it tidy)
    # called by → write_today_post
    return days_dir / day.strftime("%Y") / day.strftime("%m-%d.md")


def build_first_entry(day: datetime, line: str, emoji: str) -> str:
    """
    LEARN: the text of a new day's file

    called by → write_today_post, the first time that day
    "Tue 3 Nov 2026": %a weekday, %b month, %Y year
    f"{day.day}" → 3 (no leading zero, unlike %d → 03)
    """
    title = f"{day.strftime('%a')} {day.day} {day.strftime('%b %Y')}"
    return f"# {title} {emoji}\n\n> {line}\n"


def build_extra_entry(day: datetime, line: str) -> str:
    # a second post on the same day: a divider, the time, the line
    # called by → write_today_post, when today's file already exists
    return f"\n---\n**{day.strftime('%H:%M')} UTC** · {line}\n"


def write_today_post(days_dir: Path, day: datetime, line: str, emoji: str) -> Path:
    """
    LEARN: create today's file, or add to it if it already exists

    called by → main
    gives back → the file's path (main prints it into the run's log)

    parents=True, exist_ok=True → make days/2026/ if missing, no error if not
    "a" = append: add to the end of the file instead of replacing it
    """
    post_path = find_post_path(days_dir, day)
    post_path.parent.mkdir(parents=True, exist_ok=True)
    if not post_path.exists():
        post_path.write_text(build_first_entry(day, line, emoji), encoding="utf-8")
        return post_path

    with post_path.open("a", encoding="utf-8") as post_file:
        post_file.write(build_extra_entry(day, line))

    return post_path


def main() -> None:
    """
    LEARN: the whole job

    called by → daily.yml ("python3 daily.py")
      1. your own message (Run now with a message)?  → use it
         otherwise, today's first run → today's line from content.txt
         a later run today → a different line (pick_line_for_extra_run)
      2. write / add to today's file
    datetime.now(UTC) → the current time in UTC, the same clock GitHub's
      contribution graph uses for its days
    os.environ.get(name, "") → an environment variable, or "" if it isn't set
    """
    today = datetime.now(UTC)
    message = os.environ.get(MESSAGE_VARIABLE, "").strip()
    if message:
        line = message
    else:
        content = (
            CONTENT_FILE.read_text(encoding="utf-8") if CONTENT_FILE.exists() else ""
        )
        lines = read_content_lines(content)
        is_extra_run = find_post_path(DAYS_DIR, today).exists()
        line = (
            pick_line_for_extra_run(lines, today)
            if is_extra_run
            else pick_line_for_day(lines, today)
        )

    post_path = write_today_post(
        days_dir=DAYS_DIR, day=today, line=line, emoji=pick_emoji_for_day(today)
    )
    # print → shows up in the run's log on GitHub (Actions tab → the run)
    print(f"Wrote {post_path.relative_to(REPO_DIR)}: {line}")


# LEARN: run main() only when started as a script (python3 daily.py),
#   not when another file imports this one (our tests do that)
if __name__ == "__main__":
    main()
