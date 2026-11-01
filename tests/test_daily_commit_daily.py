# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks daily_commit/repo_template/daily.py (the script
#   GitHub runs daily) with posts written into tmp_path, never a real repo
#   read next → tests/test_daily_commit_github_client.py
import importlib.util
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from types import ModuleType

import pytest

TEMPLATE_DIR = (
    Path(__file__).parent.parent / "app" / "tools" / "daily_commit" / "repo_template"
)
WORKFLOW_FILE = TEMPLATE_DIR / ".github" / "workflows" / "daily.yml"
# a fixed day for every test: Tue 3 Nov 2026, 10:42 UTC
FIXED_DAY = datetime(2026, 11, 3, 10, 42, tzinfo=UTC)


def load_daily_script() -> ModuleType:
    """
    LEARN: load daily.py from its file path
      it isn't inside a Python package (it lives in the notes repo later)
      → a normal "from app... import" can't reach it
      spec_from_file_location → "a module named X lives in this file"
      exec_module → run the file once, which defines its functions
      its main() doesn't run: that only happens under python3 daily.py
    """
    spec = importlib.util.spec_from_file_location(
        "daily_commit_daily_script", TEMPLATE_DIR / "daily.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def daily() -> ModuleType:
    return load_daily_script()


@pytest.fixture
def notes_repo(
    daily: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """
    LEARN: a pretend notes repo in tmp_path, for main()
      monkeypatch.setattr → swap a module's value for this test only
      → main() reads content.txt and writes days/ inside tmp_path
      FixedDatetime → "now" is always FIXED_DAY, so the file name is known
    """

    class FixedDatetime(datetime):
        # LEARN: @classmethod → called on the class itself (datetime.now()),
        #   like the real one; cls = the class, as self is for an instance
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return FIXED_DAY if tz is None else FIXED_DAY.astimezone(tz)

    monkeypatch.setattr(daily, "REPO_DIR", tmp_path)
    monkeypatch.setattr(daily, "CONTENT_FILE", tmp_path / "content.txt")
    monkeypatch.setattr(daily, "DAYS_DIR", tmp_path / "days")
    monkeypatch.setattr(daily, "datetime", FixedDatetime)
    monkeypatch.delenv("DAILY_MESSAGE", raising=False)
    return tmp_path


class TestDailyCommitDailyReadContentLines:
    def test_daily_commit_daily_read_content_lines_skips_comments_and_blanks(
        self, daily: ModuleType
    ) -> None:
        text = "# my list\n\n  first line  \n# another note\nsecond line\n   \n"

        assert daily.read_content_lines(text) == ["first line", "second line"]

    def test_daily_commit_daily_read_content_lines_empty_text(
        self, daily: ModuleType
    ) -> None:
        assert daily.read_content_lines("") == []


class TestDailyCommitDailyPickLineForDay:
    def test_daily_commit_daily_pick_line_for_day_same_day_same_line(
        self, daily: ModuleType
    ) -> None:
        lines = [f"line {number}" for number in range(50)]
        later_that_day = FIXED_DAY.replace(hour=23)

        first = daily.pick_line_for_day(lines, FIXED_DAY)

        assert first in lines
        assert daily.pick_line_for_day(lines, later_that_day) == first

    def test_daily_commit_daily_pick_line_for_day_changes_across_days(
        self, daily: ModuleType
    ) -> None:
        lines = [f"line {number}" for number in range(50)]
        days = [FIXED_DAY.replace(day=day) for day in range(1, 29)]

        picks = {daily.pick_line_for_day(lines, day) for day in days}

        assert len(picks) > 1

    def test_daily_commit_daily_pick_line_for_day_no_lines_uses_fallback(
        self, daily: ModuleType
    ) -> None:
        assert daily.pick_line_for_day([], FIXED_DAY) == daily.FALLBACK_LINE


class TestDailyCommitDailyPickEmojiForDay:
    def test_daily_commit_daily_pick_emoji_for_day_same_day_same_emoji(
        self, daily: ModuleType
    ) -> None:
        emoji = daily.pick_emoji_for_day(FIXED_DAY)

        assert emoji in daily.EMOJIS
        assert daily.pick_emoji_for_day(FIXED_DAY.replace(hour=1)) == emoji


class TestDailyCommitDailyFindPostPath:
    def test_daily_commit_daily_find_post_path_year_folder_and_month_day(
        self, daily: ModuleType, tmp_path: Path
    ) -> None:
        assert daily.find_post_path(tmp_path, FIXED_DAY) == (
            tmp_path / "2026" / "11-03.md"
        )


class TestDailyCommitDailyWriteTodayPost:
    def test_daily_commit_daily_write_today_post_first_run_creates_file(
        self, daily: ModuleType, tmp_path: Path
    ) -> None:
        post_path = daily.write_today_post(
            days_dir=tmp_path, day=FIXED_DAY, line="Hello", emoji="🌱"
        )

        assert post_path.read_text(encoding="utf-8") == (
            "# Tue 3 Nov 2026 🌱\n\n> Hello\n"
        )

    def test_daily_commit_daily_write_today_post_second_run_appends(
        self, daily: ModuleType, tmp_path: Path
    ) -> None:
        daily.write_today_post(days_dir=tmp_path, day=FIXED_DAY, line="Hi", emoji="🌱")

        post_path = daily.write_today_post(
            days_dir=tmp_path, day=FIXED_DAY, line="Again", emoji="🔥"
        )

        assert post_path.read_text(encoding="utf-8") == (
            "# Tue 3 Nov 2026 🌱\n\n> Hi\n\n---\n**10:42 UTC** · Again\n"
        )


class TestDailyCommitDailyMain:
    def test_daily_commit_daily_main_picks_line_from_content(
        self, daily: ModuleType, notes_repo: Path
    ) -> None:
        (notes_repo / "content.txt").write_text("# note\nOnly line\n", encoding="utf-8")

        daily.main()

        post = (notes_repo / "days" / "2026" / "11-03.md").read_text(encoding="utf-8")
        assert "> Only line" in post

    def test_daily_commit_daily_main_message_replaces_random_line(
        self, daily: ModuleType, notes_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (notes_repo / "content.txt").write_text("Only line\n", encoding="utf-8")
        monkeypatch.setenv("DAILY_MESSAGE", "  My own words  ")

        daily.main()

        post = (notes_repo / "days" / "2026" / "11-03.md").read_text(encoding="utf-8")
        assert "> My own words" in post
        assert "Only line" not in post

    def test_daily_commit_daily_main_missing_content_uses_fallback(
        self, daily: ModuleType, notes_repo: Path
    ) -> None:
        daily.main()

        post = (notes_repo / "days" / "2026" / "11-03.md").read_text(encoding="utf-8")
        assert daily.FALLBACK_LINE in post


class TestDailyCommitDailyTemplateFiles:
    def test_daily_commit_daily_template_content_has_lines(
        self, daily: ModuleType
    ) -> None:
        text = (TEMPLATE_DIR / "content.txt").read_text(encoding="utf-8")

        assert len(daily.read_content_lines(text)) >= 30

    def test_daily_commit_daily_template_workflow_message_only_via_env(self) -> None:
        # the typed message must reach the script as an environment variable,
        # never pasted into a shell command (script injection)
        workflow = WORKFLOW_FILE.read_text(encoding="utf-8")
        # comment lines (# …) only explain it → skipped
        stripped = [line.strip() for line in workflow.splitlines()]
        uses = [
            line
            for line in stripped
            if "inputs.message" in line and not line.startswith("#")
        ]

        assert uses == ["DAILY_MESSAGE: ${{ inputs.message }}"]
