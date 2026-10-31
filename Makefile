# LEARN: YOU ARE HERE
#   you type "make start_app" ▶ THIS FILE runs the real command
#   ▶ python -m app ▶ app/__main__.py
#   read next → app/__main__.py

# Short commands for everyday work. Run them from the project folder.
#
# LEARN: each "target:" line names a command; the indented lines under it are
# what runs (they must start with a TAB, not spaces). Every command calls the
# project's .venv directly, so nothing depends on an activated environment.
# .PHONY says these names are commands, not files make should look for.

# LEARN: NAME := value → a variable; $(NAME) uses it below
PYTHON := .venv/bin/python
LOG_FILE := logs/app.log
# the Mac app (see mac_app/README.md)
APP_NAME := Bao Internal Apps
BUNDLE_ID := com.nhqb.bao-internal-apps
BUILT_APP := dist/$(APP_NAME).app
# $(HOME) = your home folder → ~/Applications (Spotlight and Launchpad see it)
INSTALLED_APP := $(HOME)/Applications/$(APP_NAME).app

.PHONY: start_app test lint sync logs app_icon build_app install_app uninstall_app quit_installed_app bump_version

# open the app window
# -m app → run the "app" folder as a program (Python runs app/__main__.py)
start_app:
	$(PYTHON) -m app

# run the unit tests
test:
	$(PYTHON) -m pytest

# lint and formatting checks (reports only, changes nothing)
lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

# install exactly what uv.lock lists (run after pulling new dependencies)
sync:
	.venv/bin/uv sync --locked

# follow the log file live (Ctrl+C to stop)
# @ → don't print the command itself, only its output
# shell if: file exists (-f) → tail -f follows it; else → print a hint
logs:
	@if [ -f $(LOG_FILE) ]; then tail -f $(LOG_FILE); else echo "No logs yet: start the app once with make start_app"; fi

# raise the version number in pyproject.toml (and uv.lock)
#   make bump_version              0.1.0 → 0.1.1   (small fixes)
#   make bump_version PART=minor   0.1.0 → 0.2.0   (new features)
#   make bump_version PART=major   0.1.0 → 1.0.0   (big changes)
#   PART ?= patch → "patch" unless you give PART=… on the command line
#   industry term: "semantic versioning" (major.minor.patch)
PART ?= patch
bump_version:
	.venv/bin/uv version --bump $(PART)

# redraw the app icon (only needed after changing mac_app/make_icon.py)
app_icon:
	$(PYTHON) mac_app/make_icon.py

# build dist/Bao Internal Apps.app from the code as it is now
#   1. write the version stamp (version, time, commit) to build/build_info.json
#   2. PyInstaller follows the recipe in mac_app/bao_internal_apps.spec
#      --noconfirm → replace the last build without asking
#      --clean → start from scratch (no stale leftovers)
build_app:
	$(PYTHON) -m app.build_info build/build_info.json
	.venv/bin/pyinstaller --noconfirm --clean --distpath dist --workpath build/pyinstaller mac_app/bao_internal_apps.spec

# LEARN: ask the installed app to quit (it saves window + settings like ⌘Q),
#   then wait up to 10 s for it to be gone
#   pgrep -qf "…" → true while a process with that path is running
#   osascript = run AppleScript from the terminal; the app is named by its
#     bundle id, so a dev copy (or a not-yet-installed app) is never touched
#   a && b || true → only quit if running; never fail the make command
#   $$ → a literal $ for the shell (make uses $ for its own variables)
quit_installed_app:
	@pgrep -qf "$(INSTALLED_APP)/Contents/MacOS" && osascript -e 'tell application id "$(BUNDLE_ID)" to quit' || true
	@for attempt in $$(seq 1 20); do pgrep -qf "$(INSTALLED_APP)/Contents/MacOS" || break; sleep 0.5; done

# deploy: build → quit the running copy → replace it in ~/Applications → open it
#   ditto = macOS's copy tool that keeps everything a .app needs intact
install_app: build_app quit_installed_app
	mkdir -p "$(HOME)/Applications"
	rm -rf "$(INSTALLED_APP)"
	ditto "$(BUILT_APP)" "$(INSTALLED_APP)"
	open "$(INSTALLED_APP)"

# remove the app from ~/Applications (its settings and logs in ~/Library stay)
uninstall_app: quit_installed_app
	rm -rf "$(INSTALLED_APP)"
