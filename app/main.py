# LEARN: YOU ARE HERE
#   __main__.py ▶ THIS FILE sets everything up and opens the window
#   ▶ pywebview loads app/ui/index.html ▶ the page calls the bridge from then on
#   read next → app/paths.py
"""
Builds the window and starts the app.

LEARN: startup order (each step = one file you can open)

  settings      config.py         read .env (dev copy only)
  version       build_info.py     which version is running
  logging       logging_setup.py  open app.log
  one copy?     single_instance   already running → bring it forward, quit
  saved state   state.py          window size, sidebar, user settings
  tools         tools/__init__    make every tool (readers start here)
  bridge        bridge.py         the object the page may call
  window        pywebview         open it, load the page, run until closed

LEARN: how the window works

  pywebview = Python library that opens a real macOS window and shows a web
  page inside it (with Safari's engine, WebKit), no browser needed

    Python (this app) ◀── bridge ──▶ page (HTML / CSS / JS) in the window
"""

import logging

import webview

# LEARN: AppKit / PyObjCTools = PyObjC: Python access to Apple's macOS libs
#   (installed with pywebview; see app_icons.py for how names map)
from AppKit import NSApplication
from PyObjCTools import AppHelper

from app.bridge import AppBridge
from app.build_info import format_build_label, load_build_info
from app.config import AppSettings
from app.logging_setup import configure_app_logging
from app.paths import DATA_DIR, INSTANCE_SOCKET, STATE_FILE, UI_DIR, is_installed_app
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
# the dev copy says so in its title bar → easy to tell the two windows apart
DEV_TITLE_SUFFIX = " (dev)"
# colour shown before the page has loaded (matches the dark theme → no flash)
WINDOW_BACKGROUND = "#121211"


def run_internal_apps() -> None:
    """
    LEARN: the whole app, start to finish

    called by → app/__main__.py
    returns only when the window is closed
    """
    settings = AppSettings()
    log_file = configure_app_logging(settings)
    installed = is_installed_app()
    build_info = load_build_info(is_installed=installed)
    build_label = format_build_label(build_info)
    logger.info(f"Starting {APP_TITLE} {build_label} {installed=} {log_file=}")
    # the installed app's data folder doesn't exist on its very first start
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # already running? → ask that copy to come forward, then stop here
    guard = SingleInstanceGuard(INSTANCE_SOCKET)
    if guard.ask_running_instance_to_focus():
        logger.info("Already running, asked the open window to come forward")
        return

    store = StateStore(STATE_FILE)
    # the Logs tool shows the same file logging writes to
    tools = build_tool_registry(log_file)
    bridge = AppBridge(
        tools=tools,
        preferences=PreferencesService(store=store, tools=tools),
        store=store,
        build_info=build_info,
    )
    # reopen where it was last time, if that spot is still on a screen
    geometry = choose_window_geometry(
        saved=store.read_app_state().window,
        screens=read_connected_screen_areas(webview.screens),
        default_size=(settings.default_window_width, settings.default_window_height),
        min_size=(settings.min_window_width, settings.min_window_height),
    )
    window = create_main_window(
        title=APP_TITLE if installed else APP_TITLE + DEV_TITLE_SUFFIX,
        geometry=geometry,
        bridge=bridge,
        settings=settings,
    )

    # LEARN: events.closing += f → "when the window is closing, call f"
    #   (+= adds a listener; industry term: "event handler")
    #   lambda: … = a tiny unnamed function with no arguments
    window.events.closing += lambda: save_main_window_state(window=window, store=store)
    guard.start_listening_for_focus_requests(
        on_focus=lambda: bring_main_window_to_front(window)
    )

    # LEARN: try / finally → the finally part runs after the window closes,
    #   even if something crashed → the socket file is always cleaned up
    try:
        # LEARN: start() = run the macOS "event loop" until the window closes
        #   event loop = waits for clicks, key presses, redraws, and handles
        #   them; must run on the main thread (macOS rule)
        #   → this line blocks: nothing below runs while the app is open
        # http_server=True → serve the ui folder from a private local address
        #   so the page can load its own .css / .js files
        webview.start(http_server=True)
    finally:
        guard.stop_listening_for_focus_requests()
        logger.info("Stopped")


def create_main_window(
    title: str, geometry: WindowGeometry, bridge: AppBridge, settings: AppSettings
) -> webview.Window:
    """
    LEARN: open the app window

    called by → run_internal_apps, once
    gives back → the pywebview Window object

    js_api=bridge → every public method of the bridge becomes callable from
    the page's JavaScript as window.pywebview.api.<method>(…)
    """
    window = webview.create_window(
        title,
        url=str(UI_DIR / "index.html"),
        js_api=bridge,
        width=geometry.width,
        height=geometry.height,
        # x / y None → pywebview centers the window
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
    LEARN: turn macOS screen positions into top-left coordinates

    called by → run_internal_apps, once at startup
    gives back → one ScreenArea per connected screen

    macOS measures y UP from the bottom of the main screen
    pywebview measures window y DOWN from the top
      → flip the screens once so both use the same direction

      macOS          pywebview
      ▲ y            ┌──▶ x
      │              │
      └──▶ x         ▼ y
    """
    if not screens:
        return []

    # screens[0] = the main screen (the one with the menu bar)
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
    """
    LEARN: remember size + position when the window closes

    called by → pywebview, via the "closing" event
    saved to → state.json (used again at the next start)
    """
    try:
        store.save_window_state(
            WindowState(
                width=window.width, height=window.height, x=window.x, y=window.y
            )
        )
    # logger.exception → logs the error AND its full traceback (where it came
    # from); a failed save must never stop the window from closing
    except Exception:
        logger.exception("Could not save the window size and position")


def bring_main_window_to_front(window: webview.Window) -> None:
    """
    LEARN: un-minimise, show, and focus the window

    called by → single_instance.py, when a 2nd launch asks (background thread)
    """
    window.restore()
    window.show()
    # LEARN: macOS UI calls must run on the main thread
    #   we're on a background thread here → AppHelper.callAfter(f) queues f
    #   to run on the main thread at the next chance
    # activateIgnoringOtherApps_(True) → bring this app in front of others
    AppHelper.callAfter(
        lambda: NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    )
