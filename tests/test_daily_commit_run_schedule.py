# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks daily_commit/run_schedule.py: runs per day →
#   times → the cron line in daily.yml, and reading it back
#   read next → tests/test_daily_commit_tool.py
import pytest

from app.tools.daily_commit.run_schedule import (
    RUNS_PER_DAY_DEFAULT,
    build_cron_expression,
    check_runs_per_day,
    read_run_times_from_cron,
    plan_run_hours_utc,
    read_runs_per_day_from_workflow,
    write_runs_per_day_into_workflow,
)
from app.tools.daily_commit.template_sync import WORKFLOW_PATH, read_template_files

# a small daily.yml with the schedule line between other lines
WORKFLOW = 'on:\n  schedule:\n    - cron: "17 1,13 * * *"\n\n  workflow_dispatch:\n'


class TestDailyCommitRunScheduleCheckRunsPerDay:
    @pytest.mark.parametrize("runs_per_day", [0, 6, -1])
    def test_daily_commit_run_schedule_check_runs_per_day_outside_1_to_5_raises(
        self, runs_per_day: int
    ) -> None:
        with pytest.raises(ValueError, match="1 to 5"):
            check_runs_per_day(runs_per_day)

    def test_daily_commit_run_schedule_check_runs_per_day_inside_is_returned(
        self,
    ) -> None:
        assert check_runs_per_day(3) == 3


class TestDailyCommitRunSchedulePlanRunHoursUtc:
    # LEARN: 01:00-13:00 UTC = 08:00-20:00 in Vietnam, spread evenly
    @pytest.mark.parametrize(
        ("runs_per_day", "expected_hours"),
        [
            (1, [1]),
            (2, [1, 13]),
            (3, [1, 7, 13]),
            (4, [1, 5, 9, 13]),
            (5, [1, 4, 7, 10, 13]),
        ],
    )
    def test_daily_commit_run_schedule_plan_run_hours_utc_spread_evenly(
        self, runs_per_day: int, expected_hours: list[int]
    ) -> None:
        assert plan_run_hours_utc(runs_per_day) == expected_hours


class TestDailyCommitRunScheduleBuildCronExpression:
    def test_daily_commit_run_schedule_build_cron_expression_minute_17(
        self,
    ) -> None:
        assert build_cron_expression(2) == "17 1,13 * * *"

    def test_daily_commit_run_schedule_build_cron_expression_one_run(self) -> None:
        assert build_cron_expression(1) == "17 1 * * *"


class TestDailyCommitRunScheduleReadRunTimesFromCron:
    @pytest.mark.parametrize(
        ("cron", "expected_times"),
        [
            ("17 1,13 * * *", ["01:17", "13:17"]),
            # the first template's schedule → still readable
            ("0 3 * * *", ["03:00"]),
            # hours out of order / repeated → sorted, once each
            ("5 13,1,1 * * *", ["01:05", "13:05"]),
        ],
    )
    def test_daily_commit_run_schedule_read_run_times_from_cron_simple(
        self, cron: str, expected_times: list[str]
    ) -> None:
        assert read_run_times_from_cron(cron) == expected_times

    @pytest.mark.parametrize(
        "cron",
        ["*/5 * * * *", "0 3 * * 1", "0 1-5 * * *", "60 3 * * *", "0 24 * * *", ""],
    )
    def test_daily_commit_run_schedule_read_run_times_from_cron_fancy_is_empty(
        self, cron: str
    ) -> None:
        assert read_run_times_from_cron(cron) == []


class TestDailyCommitRunScheduleReadRunsPerDayFromWorkflow:
    def test_daily_commit_run_schedule_read_runs_per_day_from_workflow_two(
        self,
    ) -> None:
        assert read_runs_per_day_from_workflow(WORKFLOW) == 2

    def test_daily_commit_run_schedule_read_runs_per_day_from_workflow_old_copy(
        self,
    ) -> None:
        # the first template's "0 3 * * *" isn't one this app writes now
        old = WORKFLOW.replace("17 1,13 * * *", "0 3 * * *")

        assert read_runs_per_day_from_workflow(old) is None

    def test_daily_commit_run_schedule_read_runs_per_day_from_workflow_no_schedule(
        self,
    ) -> None:
        assert read_runs_per_day_from_workflow("on:\n  workflow_dispatch:\n") is None

    def test_daily_commit_run_schedule_read_runs_per_day_from_workflow_template(
        self,
    ) -> None:
        # the template copied to new repos starts at the default (2 a day)
        template = read_template_files()[WORKFLOW_PATH]

        assert read_runs_per_day_from_workflow(template) == RUNS_PER_DAY_DEFAULT


class TestDailyCommitRunScheduleWriteRunsPerDayIntoWorkflow:
    def test_daily_commit_run_schedule_write_runs_per_day_into_workflow_only_cron(
        self,
    ) -> None:
        written = write_runs_per_day_into_workflow(
            workflow_text=WORKFLOW, runs_per_day=4
        )

        assert written == WORKFLOW.replace("17 1,13 * * *", "17 1,5,9,13 * * *")
        assert read_runs_per_day_from_workflow(written) == 4

    def test_daily_commit_run_schedule_write_runs_per_day_into_workflow_template(
        self,
    ) -> None:
        # the real template: every line but the schedule line stays the same
        template = read_template_files()[WORKFLOW_PATH]

        written = write_runs_per_day_into_workflow(
            workflow_text=template, runs_per_day=5
        )

        changed = [
            (old, new)
            for old, new in zip(
                template.splitlines(), written.splitlines(), strict=True
            )
            if old != new
        ]
        assert changed == [
            ('    - cron: "17 1,13 * * *"', '    - cron: "17 1,4,7,10,13 * * *"')
        ]

    def test_daily_commit_run_schedule_write_runs_per_day_into_workflow_no_line(
        self,
    ) -> None:
        with pytest.raises(ValueError, match="no schedule line"):
            write_runs_per_day_into_workflow(
                workflow_text="on:\n  workflow_dispatch:\n", runs_per_day=2
            )

    def test_daily_commit_run_schedule_write_runs_per_day_into_workflow_bad_count(
        self,
    ) -> None:
        with pytest.raises(ValueError, match="1 to 5"):
            write_runs_per_day_into_workflow(workflow_text=WORKFLOW, runs_per_day=9)
