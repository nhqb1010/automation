from app.tools.system_monitor.history import KeyedRollingHistory, RollingHistory
from tests.conftest import FakeClock


class TestSystemMonitorHistoryRollingHistory:
    def test_system_monitor_history_rolling_history_keeps_time_window(
        self, fake_clock: FakeClock
    ) -> None:
        history = RollingHistory(window_seconds=10, clock=fake_clock)
        history.add_sample(1.0)
        fake_clock.advance(6)
        history.add_sample(2.0)
        fake_clock.advance(6)
        history.add_sample(3.0)

        assert history.values() == [2.0, 3.0]

    def test_system_monitor_history_rolling_history_expires_without_new_samples(
        self, fake_clock: FakeClock
    ) -> None:
        history = RollingHistory(window_seconds=10, clock=fake_clock)
        history.add_sample(1.0)
        fake_clock.advance(11)

        assert history.values() == []


class TestSystemMonitorHistoryKeyedRollingHistory:
    def test_system_monitor_history_keyed_rolling_history_keep_only_keys(
        self, fake_clock: FakeClock
    ) -> None:
        history = KeyedRollingHistory(window_seconds=60, clock=fake_clock)
        history.add_sample("chrome", 10.0)
        history.add_sample("slack", 5.0)

        history.keep_only_keys({"chrome"})

        assert history.values_for("chrome") == [10.0]
        assert history.values_for("slack") == []
