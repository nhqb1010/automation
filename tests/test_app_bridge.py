# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks app/bridge.py (what the page may call)
#   read next → tests/test_system_monitor_cpu_memory.py
import logging

import pytest

from app.bridge import AppBridge
from app.build_info import BuildInfo
from app.preferences import PreferencesService
from app.state import StateStore
from app.tools.base import UnknownToolActionError
from tests.conftest import DummyTool


@pytest.fixture
def bridge(state_store: StateStore, dummy_tool: DummyTool) -> AppBridge:
    tools = [dummy_tool]
    return AppBridge(
        tools=tools,
        preferences=PreferencesService(store=state_store, tools=tools),
        store=state_store,
        build_info=BuildInfo(
            version="1.2.3",
            built_at="2026-10-29T22:40:00",
            commit="abc1234",
            is_dev=False,
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
            "is_dev": False,
        }


class TestAppBridgeLogClientError:
    def test_app_bridge_log_client_error_goes_to_log(
        self, bridge: AppBridge, caplog: pytest.LogCaptureFixture
    ) -> None:
        # LEARN: caplog = built-in pytest fixture that catches log lines
        #   caplog.text = everything logged inside the with-block
        with caplog.at_level(logging.ERROR, logger="ui"):
            bridge.log_client_error("boom", "view.js", 12)

        assert "view.js:12 boom" in caplog.text
