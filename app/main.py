"""Builds the window and starts the app."""

import logging

import webview
from AppKit import NSApplication
from PyObjCTools import AppHelper

from app.bridge import AppBridge
from app.config import AppSettings
from app.logging_setup import configure_app_logging
from app.paths import INSTANCE_SOCKET, STATE_FILE, UI_DIR
from app.preferences import PreferencesService
from app.single_instance import SingleInstanceGuard
from app.state import (
    ScreenArea,
    StateStore,
    WindowGeometry,
    WindowState,
    choose_window_geometry,
)
from app.tools import build_tool_registry

logger = logging.getLogger(__name__)

APP_TITLE = "Bao Internal Apps"
WINDOW_BACKGROUND = "#121211"


def run_internal_apps() -> None:
    settings = AppSettings()
    log_file = configure_app_logging(settings)
    logger.info(f"Starting {APP_TITLE} {log_file=}")

    guard = SingleInstanceGuard(INSTANCE_SOCKET)
    if guard.ask_running_instance_to_focus():
        logger.info("Already running, asked the open window to come forward")
        return

    store = StateStore(STATE_FILE)
    tools = build_tool_registry()
    bridge = AppBridge(
        tools=tools,
        preferences=PreferencesService(store=store, tools=tools),
        store=store,
    )
    geometry = choose_window_geometry(
        saved=store.read_app_state().window,
        screens=read_connected_screen_areas(webview.screens),
        default_size=(settings.default_window_width, settings.default_window_height),
        min_size=(settings.min_window_width, settings.min_window_height),
    )
    window = create_main_window(geometry=geometry, bridge=bridge, settings=settings)
    window.events.closing += lambda: save_main_window_state(window=window, store=store)
    guard.start_listening_for_focus_requests(
        on_focus=lambda: bring_main_window_to_front(window)
    )

    try:
        # LEARN: start() blocks and runs the macOS event loop on the main
        # thread until the window closes. http_server serves the ui folder
        # from a private local address so the page can load its own files.
        webview.start(http_server=True)
    finally:
        guard.stop_listening_for_focus_requests()
        logger.info("Stopped")


def create_main_window(
    geometry: WindowGeometry, bridge: AppBridge, settings: AppSettings
) -> webview.Window:
    window = webview.create_window(
        APP_TITLE,
        url=str(UI_DIR / "index.html"),
        js_api=bridge,
        width=geometry.width,
        height=geometry.height,
        x=geometry.x,
        y=geometry.y,
        min_size=(settings.min_window_width, settings.min_window_height),
        background_color=WINDOW_BACKGROUND,
    )
    if window is None:
        raise RuntimeError("Window creation was cancelled")

    return window


def read_connected_screen_areas(screens: list[webview.Screen]) -> list[ScreenArea]:
    """
    Convert macOS screen frames to top-left coordinates, like window positions.

    LEARN: macOS measures y upward from the bottom of the main screen, while
    pywebview reports window positions measured down from the top. Flipping
    the screens once makes the two comparable.

    Args:
        screens (list[webview.Screen]): screens from pywebview, main screen first.
    Returns:
        list[ScreenArea]: the same screens with y measured from the top.
    """
    if not screens:
        return []

    main_height = screens[0].height
    return [
        ScreenArea(
            x=screen.x,
            y=main_height - (screen.y + screen.height),
            width=screen.width,
            height=screen.height,
        )
        for screen in screens
    ]


def save_main_window_state(window: webview.Window, store: StateStore) -> None:
    try:
        store.save_window_state(
            WindowState(
                width=window.width, height=window.height, x=window.x, y=window.y
            )
        )
    except Exception:
        logger.exception("Could not save the window size and position")


def bring_main_window_to_front(window: webview.Window) -> None:
    window.restore()
    window.show()
    # LEARN: AppKit calls must happen on the main thread; callAfter queues
    # the call onto it from this background thread.
    AppHelper.callAfter(
        lambda: NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    )
