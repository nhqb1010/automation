"""Well-known locations inside the project folder."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"
UI_DIR = APP_DIR / "ui"
STATE_FILE = PROJECT_ROOT / "state.json"
ENV_FILE = PROJECT_ROOT / ".env"

# LEARN: a Unix domain socket is a file-shaped endpoint for talking between
# processes on the same machine. A second launch connects to it to ask the
# first one to come forward.
INSTANCE_SOCKET = PROJECT_ROOT / ".instance.sock"
