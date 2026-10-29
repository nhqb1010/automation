# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks recent_values.py (the last 60 s of numbers)
#   with a fake clock → no real waiting
#   read next → tests/test_system_monitor_temperature.py
from app.tools.system_monitor.recent_values import RecentValues, RecentValuesPerApp
from tests.conftest import FakeClock


class TestSystemMonitorRecentValuesRecentValues:
    def test_system_monitor_recent_values_recent_values_keeps_time_window(
        self, fake_clock: FakeClock
    ) -> None:
        # window 10 s: samples at t=0, 6, 12 → the t=0 one is too old by t=12
        recent = RecentValues(window_seconds=10, clock=fake_clock)
        recent.add_sample(1.0)
        fake_clock.advance(6)
        recent.add_sample(2.0)
        fake_clock.advance(6)
        recent.add_sample(3.0)

        assert recent.values() == [2.0, 3.0]

    def test_system_monitor_recent_values_recent_values_expires_without_new_samples(
        self, fake_clock: FakeClock
    ) -> None:
        # old values drop out on read too, not only when a new one is added
        recent = RecentValues(window_seconds=10, clock=fake_clock)
        recent.add_sample(1.0)
        fake_clock.advance(11)

        assert recent.values() == []


class TestSystemMonitorRecentValuesPerApp:
    def test_system_monitor_recent_values_per_app_keep_only_apps(
        self, fake_clock: FakeClock
    ) -> None:
        # an app that left the top list → its values are forgotten
        recent = RecentValuesPerApp(window_seconds=60, clock=fake_clock)
        recent.add_sample("chrome", 10.0)
        recent.add_sample("slack", 5.0)

        recent.keep_only_apps({"chrome"})

        assert recent.values_for("chrome") == [10.0]
        assert recent.values_for("slack") == []
