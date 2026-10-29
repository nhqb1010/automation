# LEARN: YOU ARE HERE
#   the built .app starts ▶ THIS FILE (its first Python code)
#   ▶ app/main.py run_internal_apps, exactly like make start_app
#   read next → mac_app/make_icon.py
"""
Entry point for the built Mac app.

LEARN: why a separate file
  make start_app runs "python -m app" (the app folder as a program)
  PyInstaller needs one plain script to start from → this file
  it does nothing else, so dev and installed run the same code
"""

from app.main import run_internal_apps

run_internal_apps()
