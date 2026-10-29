# LEARN: YOU ARE HERE
#   "make start_app" ▶ "python -m app" ▶ THIS FILE ▶ starts the app (main.py)
#   read next → app/main.py
"""
Entry point for: python -m app

LEARN: "python -m app" = run the package "app" as a program
  Python looks for app/__main__.py and runs it → this file
"""

from app.main import run_internal_apps

# LEARN: __name__ = "__main__" only when this file is run as the program
#   imported by something else → this block is skipped
#   industry term: "main guard"
if __name__ == "__main__":
    run_internal_apps()
