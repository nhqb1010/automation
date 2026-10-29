# LEARN: YOU ARE HERE
#   Settings page "Open at login" ▶ bridge ▶ THIS FILE asks macOS to add or
#   remove the app from Login Items ▶ macOS opens it at every login
#   read next → app/logging_setup.py
"""
Open the installed app automatically when you log in.

LEARN: Login Items (System Settings → General → Login Items)

  SMAppService = Apple's way for an app to add ITSELF to Login Items
    (macOS 13+, no password; macOS shows a "Login item added" notice)
  it only works for a real .app → the dev copy (make start_app) can't

  status from macOS          what the Settings switch shows
  enabled                 →  On
  not registered          →  Off
  requires approval       →  Off + "allow it in System Settings"
  not found / dev copy    →  greyed out + why
"""

import logging
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel
from ServiceManagement import SMAppService

logger = logging.getLogger(__name__)

# the numbers macOS uses for each status (SMAppServiceStatus…)
STATUS_NOT_REGISTERED = 0
STATUS_ENABLED = 1
STATUS_REQUIRES_APPROVAL = 2
STATUS_NOT_FOUND = 3

type LoginItemState = Literal["on", "off", "needs_approval", "unavailable"]

DEV_COPY_NOTE = "Only the installed app can open at login (make install_app)."
APPROVAL_NOTE = "Allow it in System Settings → General → Login Items."
NOT_FOUND_NOTE = "macOS can't find this app. Reinstall it with make install_app."


class LoginItemStatus(BaseModel):
    """
    LEARN: what the Settings page shows for "Open at login"

    made by → describe_login_item_status
    note → a short explanation under the switch, or None
    """

    state: LoginItemState
    note: str | None = None


# macOS status number → what the switch shows (installed app only)
STATUS_BY_CODE: dict[int, LoginItemStatus] = {
    STATUS_ENABLED: LoginItemStatus(state="on"),
    STATUS_NOT_REGISTERED: LoginItemStatus(state="off"),
    STATUS_REQUIRES_APPROVAL: LoginItemStatus(
        state="needs_approval", note=APPROVAL_NOTE
    ),
}


def describe_login_item_status(status_code: int, is_installed: bool) -> LoginItemStatus:
    """
    LEARN: macOS's status number → what the switch should show

    called by → LoginItemManager (and tests, with plain numbers)
    """
    if not is_installed:
        return LoginItemStatus(state="unavailable", note=DEV_COPY_NOTE)

    # .get(key, default) → anything unexpected counts as "not found"
    return STATUS_BY_CODE.get(
        status_code, LoginItemStatus(state="unavailable", note=NOT_FOUND_NOTE)
    )


class LoginItemManager:
    """
    LEARN: reads and changes the app's Login Item

    made by → main.py, once at startup
    called by → bridge.get_open_at_login / set_open_at_login
    open_service → gives the macOS service object; tests pass a fake
    """

    def __init__(
        self,
        is_installed: bool,
        open_service: Callable[[], Any] = SMAppService.mainAppService,
    ) -> None:
        self._is_installed = is_installed
        self._open_service = open_service

    def read_login_item_status(self) -> LoginItemStatus:
        if not self._is_installed:
            return describe_login_item_status(
                status_code=STATUS_NOT_FOUND, is_installed=False
            )

        return describe_login_item_status(
            status_code=int(self._open_service().status()), is_installed=True
        )

    def set_open_at_login(self, enabled: bool) -> LoginItemStatus:
        """
        LEARN: turn opening at login on or off

        gives back → the status afterwards (so the switch shows the truth)
        PyObjC: Apple's "…AndReturnError:" methods give back (ok, error)
        a failure is logged and the real status is shown, never a crash
        """
        if not self._is_installed:
            return self.read_login_item_status()

        service = self._open_service()
        if enabled:
            ok, error = service.registerAndReturnError_(None)
        else:
            ok, error = service.unregisterAndReturnError_(None)

        if not ok:
            logger.warning(f"Could not change Open at login {enabled=} {error=}")
        else:
            logger.info(f"Open at login changed {enabled=}")

        return self.read_login_item_status()
