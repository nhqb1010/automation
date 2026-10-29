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

.PHONY: start_app test lint sync logs

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
