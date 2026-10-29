# LEARN: YOU ARE HERE
#   main.py at startup ▶ THIS FILE says which version is running
#   ▶ bridge get_app_info ▶ the line at the bottom of the Settings page
#   (make build_app also runs THIS FILE directly to write the stamp file)
#   read next → app/logging_setup.py
"""
Which version of the app is running, and when it was built.

LEARN: how the stamp gets into the installed app

  make build_app
    └─ python -m app.build_info build/build_info.json  (THIS FILE, main below)
         { "version": "0.1.0", "built_at": "…", "commit": "ff822d1" }
    └─ PyInstaller copies it into the .app as app/build_info.json

  installed app → reads that file → "Version 0.1.0 · built 29 Oct 22:40 · ff822d1"
  dev copy      → no file → asks pyproject.toml and git → "Version 0.1.0 · dev · …"
"""

import logging
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.paths import APP_DIR, PROJECT_ROOT, PYPROJECT_FILE

logger = logging.getLogger(__name__)

BUILD_INFO_FILE = APP_DIR / "build_info.json"
GIT_PATH = "/usr/bin/git"
# "29 Oct 22:40" (strftime codes: %d day, %b month name, %H:%M time)
BUILT_AT_DISPLAY_FORMAT = "%d %b %H:%M"


class BuildInfo(BaseModel):
    """
    LEARN: the version stamp

    made by → load_build_info (app) or collect_build_info (the build)
    built_at → ISO time text, e.g. "2026-10-29T22:40:00"; None in dev
    commit → short git commit id, e.g. "ff822d1"; None if git isn't there
    """

    version: str
    built_at: str | None
    commit: str | None
    is_dev: bool


def read_project_version(pyproject_file: Path) -> str:
    """
    LEARN: the version line from pyproject.toml ([project] version = "0.1.0")

    tomllib = Python's built-in TOML reader; "rb" → it wants bytes
    """
    with pyproject_file.open("rb") as file:
        return str(tomllib.load(file)["project"]["version"])


def read_git_commit(project_root: Path) -> str | None:
    """
    LEARN: the short id of the commit the code is on, or None

    git rev-parse --short HEAD → e.g. "ff822d1"
    no git / not a repo / too slow → None (the stamp just leaves it out)
    """
    try:
        result = subprocess.run(
            [GIT_PATH, "rev-parse", "--short", "HEAD"],
            capture_output=True,
            check=True,
            cwd=project_root,
            text=True,
            timeout=2,
        )
    except OSError, subprocess.SubprocessError:
        return None

    return result.stdout.strip() or None


def collect_build_info(is_dev: bool) -> BuildInfo:
    """
    LEARN: work out the stamp from the project folder

    called by → load_build_info (dev copy), write_build_info_file (the build)
    is_dev False → also records the build time (now)
    datetime.now().isoformat(timespec="seconds") → "2026-10-29T22:40:00"
    """
    return BuildInfo(
        version=read_project_version(PYPROJECT_FILE),
        built_at=None if is_dev else datetime.now().isoformat(timespec="seconds"),
        commit=read_git_commit(PROJECT_ROOT),
        is_dev=is_dev,
    )


def load_build_info(
    is_installed: bool, build_info_file: Path = BUILD_INFO_FILE
) -> BuildInfo:
    """
    LEARN: the stamp for THIS copy

    called by → main.py, once at startup
      installed → the file the build put inside the app
      dev       → collected from pyproject.toml + git right now
    a missing or broken file in the installed app → "unknown" (never a crash)
    """
    if not is_installed:
        return collect_build_info(is_dev=True)

    try:
        # model_validate_json(text) → check JSON text straight into the model
        return BuildInfo.model_validate_json(build_info_file.read_text("utf-8"))
    except (OSError, ValidationError) as error:
        logger.warning(f"Build info unreadable {error=}")
        return BuildInfo(version="unknown", built_at=None, commit=None, is_dev=False)


def format_build_label(info: BuildInfo) -> str:
    """
    LEARN: the stamp as one line of text

    called by → bridge.get_app_info (Settings page), main.py (startup log)
      "Version 0.1.0 · built 29 Oct 22:40 · ff822d1"   installed
      "Version 0.1.0 · dev · ff822d1"                   make start_app
    datetime.fromisoformat(text) → read the time back; strftime → format it
    """
    parts = [f"Version {info.version}"]
    if info.is_dev:
        parts.append("dev")
    elif info.built_at:
        built_at = datetime.fromisoformat(info.built_at)
        parts.append(f"built {built_at.strftime(BUILT_AT_DISPLAY_FORMAT)}")

    if info.commit:
        parts.append(info.commit)

    return " · ".join(parts)


def write_build_info_file(output_file: Path) -> None:
    """
    LEARN: save the stamp for the app being built

    called by → the block below, from make build_app
    output → build/build_info.json ▶ packed into the .app by PyInstaller
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)
    info = collect_build_info(is_dev=False)
    output_file.write_text(info.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"Wrote build info {output_file=} {info.version=} {info.commit=}")


# LEARN: runs only for "python -m app.build_info <file>", not on import
#   -m → run a module by its import name (so "from app…" imports work)
#   sys.argv = the command's words: ["…/build_info.py", "build/build_info.json"]
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="{message}", style="{")
    write_build_info_file(Path(sys.argv[1]))
