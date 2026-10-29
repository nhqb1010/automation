# LEARN: YOU ARE HERE
#   main.py / config.py / state.py ▶ THIS FILE ▶ where every file lives
#   (and which copy is running: dev or the installed Mac app)
#   read next → app/config.py
"""
Well-known locations: the app's own files, and where it keeps its data.

LEARN: one place for paths → no file has to guess where things live

LEARN: two copies of the same code, two homes for their data

                     make start_app (dev)        installed .app
  settings, state    project folder              ~/Library/Application Support/
                                                   Bao Internal Apps/
  logs               project folder/logs         ~/Library/Logs/Bao Internal Apps/
  .env               project folder/.env         not used (defaults only)

  → testing in dev never touches the installed app's settings or logs
  ~/Library/… = the standard macOS places for app data and logs
"""

import sys
from dataclasses import dataclass

# LEARN: Path = a file / folder location as an object
#   Path("a") / "b" → joins them: "a/b" (the / is overloaded for paths)
from pathlib import Path

APP_NAME = "Bao Internal Apps"

# LEARN: __file__ = this file's own path
#   .resolve() → full absolute path
#   .parent.parent → up two folders: app/paths.py → app/ → project folder
#   inside the installed app this is the app's bundled code folder instead
#   (the ui files are copied there by the build, see mac_app/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"
UI_DIR = APP_DIR / "ui"
PYPROJECT_FILE = PROJECT_ROOT / "pyproject.toml"


@dataclass(frozen=True)
class AppLocations:
    """
    LEARN: where this copy of the app keeps its data

    made by → choose_app_locations, once when this file is imported
    env_file None → no .env is read (the installed app)
    """

    data_dir: Path
    default_log_dir: Path
    env_file: Path | None


def is_installed_app() -> bool:
    """
    LEARN: True when running as the built Mac app, False for make start_app

    PyInstaller (the tool that builds the .app) sets sys.frozen = True
    getattr(obj, "name", default) → obj.name, or default if it doesn't exist
    industry term: a "frozen" app = Python + code packed into one program
    """
    return bool(getattr(sys, "frozen", False))


def choose_app_locations(
    is_installed: bool, home: Path, project_root: Path
) -> AppLocations:
    """
    LEARN: pick the data / log / .env locations for this copy

    called by → this file, once at import (and by tests, with fake folders)
    gives back → AppLocations
    """
    if is_installed:
        return AppLocations(
            data_dir=home / "Library" / "Application Support" / APP_NAME,
            default_log_dir=home / "Library" / "Logs" / APP_NAME,
            env_file=None,
        )

    return AppLocations(
        data_dir=project_root,
        default_log_dir=project_root / "logs",
        env_file=project_root / ".env",
    )


# Path.home() → your home folder, e.g. /Users/you
LOCATIONS = choose_app_locations(
    is_installed=is_installed_app(), home=Path.home(), project_root=PROJECT_ROOT
)
DATA_DIR = LOCATIONS.data_dir
# saved window size, sidebar state, user settings (see app/state.py)
STATE_FILE = DATA_DIR / "state.json"
# developer settings (see app/config.py and example.env); None when installed
ENV_FILE = LOCATIONS.env_file
DEFAULT_LOG_DIR = LOCATIONS.default_log_dir

# LEARN: Unix domain socket = a file-shaped "phone line" between two
#   programs on the same Mac
#   the running app listens on it; a 2nd launch calls it → "come forward"
#   (see app/single_instance.py)
#   dev and installed copies use different sockets → both can be open
INSTANCE_SOCKET = DATA_DIR / ".instance.sock"
