# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks daily_commit/streak_stats.py (streak, calendar,
#   minutes) with made-up dates and runs
#   read next → tests/test_daily_commit_template_sync.py
from datetime import UTC, date, datetime, timedelta

from app.tools.daily_commit.models import WorkflowRun
from app.tools.daily_commit.streak_stats import (
    build_streak_calendar,
    classify_minutes_level,
    count_current_streak,
    count_longest_streak,
    estimate_actions_minutes,
    read_posted_days,
    summarize_workflow_run,
)

# Tue 3 Nov 2026
TODAY = date(2026, 11, 3)
NOW = datetime(2026, 11, 3, 10, 0, tzinfo=UTC)


def days_before_today(*offsets: int) -> set[date]:
    # days_before_today(0, 1) → {today, yesterday}
    return {TODAY - timedelta(days=offset) for offset in offsets}


def build_run(created_at: datetime, duration_seconds: int | None) -> WorkflowRun:
    return WorkflowRun(
        status="completed",
        conclusion="success",
        event="schedule",
        created_at=created_at,
        duration_seconds=duration_seconds,
        html_url="",
    )


class TestDailyCommitStreakStatsReadPostedDays:
    def test_daily_commit_streak_stats_read_posted_days_from_names(self) -> None:
        posted = read_posted_days(
            {"2026": ["11-02.md", "11-03.md", "README.md"], "2025": ["12-31.md"]}
        )

        assert posted == {date(2026, 11, 2), date(2026, 11, 3), date(2025, 12, 31)}

    def test_daily_commit_streak_stats_read_posted_days_skips_bad_names(self) -> None:
        posted = read_posted_days(
            {"2026": ["02-30.md", "1-3.md"], "notes": ["11-03.md"]}
        )

        assert posted == set()


class TestDailyCommitStreakStatsCountCurrentStreak:
    def test_daily_commit_streak_stats_count_current_streak_includes_today(
        self,
    ) -> None:
        assert count_current_streak(posted=days_before_today(0, 1, 2), today=TODAY) == 3

    def test_daily_commit_streak_stats_count_current_streak_today_not_yet(self) -> None:
        # today's run hasn't happened yet → the streak up to yesterday still counts
        assert count_current_streak(posted=days_before_today(1, 2), today=TODAY) == 2

    def test_daily_commit_streak_stats_count_current_streak_gap_resets(self) -> None:
        assert count_current_streak(posted=days_before_today(0, 2, 3), today=TODAY) == 1

    def test_daily_commit_streak_stats_count_current_streak_none(self) -> None:
        assert count_current_streak(posted=days_before_today(2, 3), today=TODAY) == 0


class TestDailyCommitStreakStatsCountLongestStreak:
    def test_daily_commit_streak_stats_count_longest_streak_best_run(self) -> None:
        posted = days_before_today(0, 1, 3, 4, 5, 7)

        assert count_longest_streak(posted) == 3

    def test_daily_commit_streak_stats_count_longest_streak_no_posts(self) -> None:
        assert count_longest_streak(set()) == 0


class TestDailyCommitStreakStatsBuildStreakCalendar:
    def test_daily_commit_streak_stats_build_streak_calendar_twelve_weeks_from_monday(
        self,
    ) -> None:
        calendar = build_streak_calendar(posted=set(), today=TODAY)

        assert len(calendar) == 84
        assert calendar[0].day.weekday() == 0
        assert calendar[-1].day == date(2026, 11, 8)

    def test_daily_commit_streak_stats_build_streak_calendar_marks_posted_and_future(
        self,
    ) -> None:
        calendar = build_streak_calendar(posted={TODAY}, today=TODAY)
        by_day = {square.day: square for square in calendar}

        assert by_day[TODAY].posted is True
        assert by_day[TODAY].is_future is False
        assert by_day[TODAY + timedelta(days=1)].is_future is True


class TestDailyCommitStreakStatsSummarizeWorkflowRun:
    def test_daily_commit_streak_stats_summarize_workflow_run_duration(self) -> None:
        run = summarize_workflow_run(
            {
                "status": "completed",
                "conclusion": "success",
                "event": "schedule",
                "created_at": "2026-11-03T03:00:00Z",
                "run_started_at": "2026-11-03T03:00:05Z",
                "updated_at": "2026-11-03T03:00:20Z",
                "html_url": "https://github.com/run/1",
            }
        )

        assert run.duration_seconds == 15
        assert run.created_at == datetime(2026, 11, 3, 3, 0, tzinfo=UTC)

    def test_daily_commit_streak_stats_summarize_workflow_run_still_running(
        self,
    ) -> None:
        run = summarize_workflow_run(
            {
                "status": "in_progress",
                "event": "workflow_dispatch",
                "created_at": "2026-11-03T03:00:00Z",
                "run_started_at": "2026-11-03T03:00:05Z",
                "updated_at": "2026-11-03T03:00:09Z",
            }
        )

        assert run.duration_seconds is None
        assert run.conclusion is None


class TestDailyCommitStreakStatsEstimateActionsMinutes:
    def test_daily_commit_streak_stats_estimate_actions_minutes_rounds_up_per_run(
        self,
    ) -> None:
        runs = [
            build_run(created_at=NOW, duration_seconds=15),
            build_run(created_at=NOW, duration_seconds=61),
            build_run(created_at=NOW, duration_seconds=0),
        ]

        usage = estimate_actions_minutes(runs=runs, now=NOW, is_private=True)

        # 15 s → 1, 61 s → 2, 0 s → 1
        assert usage.used_minutes == 4
        assert usage.limit_minutes == 2000
        assert usage.run_count == 3
        assert usage.level == "ok"

    def test_daily_commit_streak_stats_estimate_actions_minutes_only_this_month(
        self,
    ) -> None:
        last_month = datetime(2026, 10, 31, 23, 0, tzinfo=UTC)
        runs = [
            build_run(created_at=last_month, duration_seconds=30),
            build_run(created_at=NOW, duration_seconds=None),
        ]

        usage = estimate_actions_minutes(runs=runs, now=NOW, is_private=True)

        assert usage.used_minutes == 0
        assert usage.run_count == 0

    def test_daily_commit_streak_stats_estimate_actions_minutes_public_is_free(
        self,
    ) -> None:
        runs = [build_run(created_at=NOW, duration_seconds=20)]

        usage = estimate_actions_minutes(runs=runs, now=NOW, is_private=False)

        assert usage.level == "free"
        assert usage.limit_minutes is None
        assert usage.used_minutes == 1


class TestDailyCommitStreakStatsClassifyMinutesLevel:
    def test_daily_commit_streak_stats_classify_minutes_level_thresholds(self) -> None:
        assert classify_minutes_level(74.9) == "ok"
        assert classify_minutes_level(75) == "warning"
        assert classify_minutes_level(89.9) == "warning"
        assert classify_minutes_level(90) == "critical"
