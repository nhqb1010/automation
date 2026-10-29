# LEARN: YOU ARE HERE
#   main.py / config.py / state.py ▶ THIS FILE ▶ where every file lives
#   read next → app/config.py
"""
Well-known locations inside the project folder.

LEARN: one place for paths → no file has to guess where things live
"""

# LEARN: Path = a file / folder location as an object
#   Path("a") / "b" → joins them: "a/b" (the / is overloaded for paths)
from pathlib import Path

# LEARN: __file__ = this file's own path
#   .resolve() → full absolute path
#   .parent.parent → up two folders: app/paths.py → app/ → project folder
PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"
UI_DIR = APP_DIR / "ui"
# saved window size, sidebar state, user settings (see app/state.py)
STATE_FILE = PROJECT_ROOT / "state.json"
# developer settings (see app/config.py and example.env)
ENV_FILE = PROJECT_ROOT / ".env"

# LEARN: Unix domain socket = a file-shaped "phone line" between two
#   programs on the same Mac
#   the running app listens on it; a 2nd launch calls it → "come forward"
#   (see app/single_instance.py)
INSTANCE_SOCKET = PROJECT_ROOT / ".instance.sock"
