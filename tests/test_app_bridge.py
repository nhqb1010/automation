# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks app/bridge.py (what the page may call)
#   read next → tests/test_system_monitor_cpu_memory.py
import logging

import pytest

from app.app_usage import AppUsageMonitor
from app.bridge import AppBridge, AppServices
from app.build_info import BuildInfo
from app.logging_setup import ErrorCountingHandler
from app.login_item import LoginItemManager
from app.preferences import PreferencesService
from app.state import StateStore
from app.tools.base import UnknownToolActionError
from tests.conftest import (
    DummyTool,
    FakeClock,
    FakeLoginService,
    FakeMeasuredProcess,
)


@pytest.fixture
def error_counter() -> ErrorCountingHandler:
    return ErrorCountingHandler()


@pytest.fixture
def bridge(
    state_store: StateStore,
    dummy_tool: DummyTool,
    error_counter: ErrorCountingHandler,
    fake_clock: FakeClock,
) -> AppBridge:
    tools = [dummy_tool]
    process = FakeMeasuredProcess(cpu_percent=4.0, rss=1000)
    return AppBridge(
        tools=tools,
        preferences=PreferencesService(store=state_store, tools=tools),
        store=state_store,
        services=AppServices(
            build_info=BuildInfo(
                version="1.2.3",
                built_at="2026-10-29T22:40:00",
                commit="abc1234",
                is_dev=False,
            ),
            app_usage=AppUsageMonitor(
                own_pid=1,
                find_helper_pids=lambda pid: [],
                open_process=lambda pid: process,
                cpu_count=2,
                clock=fake_clock,
            ),
            login_item=LoginItemManager(
                is_installed=True, open_service=lambda: FakeLoginService(0)
            ),
            error_counter=error_counter,
        ),
    )


class TestAppBridgeTools:
    def test_app_bridge_list_tools(self, bridge: AppBridge) -> None:
        assert bridge.list_tools() == [
            {
                "id": "dummy",
                "name": "Dummy",
                "icon": "activity",
                "description": "test tool",
            }
        ]

    def test_app_bridge_bridge_exposes_no_public_attributes(
        self, bridge: AppBridge
    ) -> None:
        # pywebview exposes every public attribute to the page, so state stays private
        # vars(obj) → the object's attributes as a dict (names → values)
        public = [name for name in vars(bridge) if not name.startswith("_")]

        assert public == []


class TestAppBridgeCall:
    def test_app_bridge_call_runs_declared_action(self, bridge: AppBridge) -> None:
        assert bridge.call("dummy", "echo_text", {"text": "hi"}) == {"text": "hi"}

    def test_app_bridge_call_unknown_tool_rejected(self, bridge: AppBridge) -> None:
        with pytest.raises(UnknownToolActionError):
            bridge.call("nope", "echo_text", {})

    def test_app_bridge_call_undeclared_method_rejected(
        self, bridge: AppBridge
    ) -> None:
        with pytest.raises(UnknownToolActionError):
            bridge.call("dummy", "secret_helper", {})


class TestAppBridgeUiState:
    def test_app_bridge_ui_state_round_trip(self, bridge: AppBridge) -> None:
        bridge.update_ui_state({"sidebar_collapsed": True, "last_tool": "dummy"})

        assert bridge.get_ui_state() == {
            "sidebar_collapsed": True,
            "last_tool": "dummy",
        }


class TestAppBridgeAppInfo:
    def test_app_bridge_app_info_label(self, bridge: AppBridge) -> None:
        assert bridge.get_app_info() == {
            "label": "Version 1.2.3 · built 29 Oct 22:40 · abc1234",
            "short_label": "v1.2.3",
            "is_dev": False,
        }


class TestAppBridgeAppUsage:
    def test_app_bridge_app_usage_reading(self, bridge: AppBridge) -> None:
        usage = bridge.get_app_usage()

        # 4 % of one core, shared across 2 cores
        assert usage["cpu_percent"] == 2.0
        assert usage["memory_bytes"] == 1000


class TestAppBridgeOpenAtLogin:
    def test_app_bridge_open_at_login_status(self, bridge: AppBridge) -> None:
        assert bridge.get_open_at_login() == {"state": "off", "note": None}


class TestAppBridgeErrorBadge:
    def test_app_bridge_error_badge_counts_and_clears(
        self, bridge: AppBridge, error_counter: ErrorCountingHandler
    ) -> None:
        error_counter.handle(
            logging.LogRecord("x", logging.ERROR, __file__, 1, "boom", None, None)
        )

        before = bridge.get_unseen_error_count()
        bridge.mark_errors_seen()

        assert before == 1
        assert bridge.get_unseen_error_count() == 0


class TestAppBridgeLogClientError:
    def test_app_bridge_log_client_error_goes_to_log(
        self, bridge: AppBridge, caplog: pytest.LogCaptureFixture
    ) -> None:
        # LEARN: caplog = built-in pytest fixture that catches log lines
        #   caplog.text = everything logged inside the with-block
        with caplog.at_level(logging.ERROR, logger="ui"):
            bridge.log_client_error("boom", "view.js", 12)

        assert "view.js:12 boom" in caplog.text
