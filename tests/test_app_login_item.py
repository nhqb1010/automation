# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks app/login_item.py ("Open at login") with a
#   pretend macOS service → never touches your real Login Items
#   read next → tests/test_app_logging_setup.py
from app.login_item import (
    APPROVAL_NOTE,
    DEV_COPY_NOTE,
    LoginItemManager,
    describe_login_item_status,
)
from tests.conftest import FakeLoginService


class TestAppLoginItemDescribeLoginItemStatus:
    def test_app_login_item_describe_login_item_status_installed(self) -> None:
        def state_for(code: int) -> str:
            return describe_login_item_status(status_code=code, is_installed=True).state

        assert state_for(1) == "on"
        assert state_for(0) == "off"
        assert state_for(2) == "needs_approval"
        assert state_for(3) == "unavailable"

    def test_app_login_item_describe_login_item_status_needs_approval_note(
        self,
    ) -> None:
        status = describe_login_item_status(status_code=2, is_installed=True)

        assert status.note == APPROVAL_NOTE

    def test_app_login_item_describe_login_item_status_dev_copy(self) -> None:
        status = describe_login_item_status(status_code=1, is_installed=False)

        assert status.state == "unavailable"
        assert status.note == DEV_COPY_NOTE


class TestAppLoginItemManager:
    def test_app_login_item_manager_turn_on_and_off(self) -> None:
        service = FakeLoginService(status_code=0)
        manager = LoginItemManager(is_installed=True, open_service=lambda: service)

        turned_on = manager.set_open_at_login(enabled=True)
        turned_off = manager.set_open_at_login(enabled=False)

        assert turned_on.state == "on"
        assert turned_off.state == "off"
        assert service.calls == ["register", "unregister"]

    def test_app_login_item_manager_refused_keeps_real_status(self) -> None:
        service = FakeLoginService(status_code=0, fail=True)
        manager = LoginItemManager(is_installed=True, open_service=lambda: service)

        status = manager.set_open_at_login(enabled=True)

        assert status.state == "off"

    def test_app_login_item_manager_dev_copy_never_asks_macos(self) -> None:
        service = FakeLoginService(status_code=1)
        manager = LoginItemManager(is_installed=False, open_service=lambda: service)

        status = manager.set_open_at_login(enabled=True)

        assert status.state == "unavailable"
        assert service.calls == []
