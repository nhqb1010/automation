# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks daily_commit/template_sync.py: which template
#   files are new / changed / same / kept, and what gets committed
#   read next → tests/test_daily_commit_tool.py
from datetime import UTC, datetime, timedelta

from app.tools.daily_commit.template_sync import (
    TEMPLATE_PATHS,
    compare_template_file,
    load_daily_script,
    pick_files_to_commit,
    plan_template_sync,
    preview_next_post,
    read_template_files,
)

TEMPLATE = {"daily.py": "print(2)\n", "content.txt": "line\n"}


class TestDailyCommitTemplateSyncReadTemplateFiles:
    def test_daily_commit_template_sync_read_template_files_has_every_path(
        self,
    ) -> None:
        files = read_template_files()

        assert list(files) == list(TEMPLATE_PATHS)
        assert "workflow_dispatch" in files[".github/workflows/daily.yml"]


class TestDailyCommitTemplateSyncCompareTemplateFile:
    def test_daily_commit_template_sync_compare_template_file_missing_is_new(
        self,
    ) -> None:
        change = compare_template_file(
            path="daily.py", template_text="print(2)\n", repo_text=None
        )

        assert change.status == "new"
        assert "+print(2)" in change.diff

    def test_daily_commit_template_sync_compare_template_file_changed_has_diff(
        self,
    ) -> None:
        change = compare_template_file(
            path="daily.py", template_text="print(2)\n", repo_text="print(1)\n"
        )

        assert change.status == "changed"
        assert "-print(1)" in change.diff
        assert "+print(2)" in change.diff

    def test_daily_commit_template_sync_compare_template_file_same(self) -> None:
        change = compare_template_file(
            path="daily.py", template_text="x\n", repo_text="x\n"
        )

        assert change.status == "same"
        assert change.diff == ""

    def test_daily_commit_template_sync_compare_template_file_content_is_kept(
        self,
    ) -> None:
        change = compare_template_file(
            path="content.txt", template_text="template\n", repo_text="mine\n"
        )

        assert change.status == "kept"


class TestDailyCommitTemplateSyncPlanTemplateSync:
    def test_daily_commit_template_sync_plan_template_sync_empty_repo(self) -> None:
        plan = plan_template_sync(template_files=TEMPLATE, repo_files={})

        assert [change.status for change in plan.changes] == ["new", "new"]
        assert plan.up_to_date is False
        assert pick_files_to_commit(plan=plan, template_files=TEMPLATE) == TEMPLATE

    def test_daily_commit_template_sync_plan_template_sync_never_commits_content(
        self,
    ) -> None:
        plan = plan_template_sync(
            template_files=TEMPLATE,
            repo_files={"daily.py": "print(1)\n", "content.txt": "mine\n"},
        )

        files = pick_files_to_commit(plan=plan, template_files=TEMPLATE)

        assert files == {"daily.py": "print(2)\n"}

    def test_daily_commit_template_sync_plan_template_sync_up_to_date(self) -> None:
        plan = plan_template_sync(
            template_files=TEMPLATE,
            repo_files={"daily.py": "print(2)\n", "content.txt": "mine\n"},
        )

        assert plan.up_to_date is True
        assert pick_files_to_commit(plan=plan, template_files=TEMPLATE) == {}


class TestDailyCommitTemplateSyncPreviewNextPost:
    NOW = datetime(2026, 11, 3, 10, 0, tzinfo=UTC)
    CONTENT = "# notes\nfirst\nsecond\nthird\n"

    def test_daily_commit_template_sync_preview_next_post_matches_daily_script(
        self,
    ) -> None:
        daily = load_daily_script()

        preview = preview_next_post(
            content_text=self.CONTENT, now=self.NOW, today_posted=False
        )

        lines = daily.read_content_lines(self.CONTENT)
        assert preview.is_today is True
        assert preview.line == daily.pick_line_for_day(lines, self.NOW)
        assert preview.emoji == daily.pick_emoji_for_day(self.NOW)
        assert preview.line_count == 3

    def test_daily_commit_template_sync_preview_next_post_after_posting_is_tomorrow(
        self,
    ) -> None:
        preview = preview_next_post(
            content_text=self.CONTENT, now=self.NOW, today_posted=True
        )

        assert preview.is_today is False
        assert preview.day == (self.NOW + timedelta(days=1)).date()
