# 006: Lighter refreshes, own-usage card, open at login, error badge, security policy

- **Status:** implemented, waiting for test run
- **Created:** 2026-10-30

## Requirement
Keep the app light on CPU and energy with settings you can tweak and a way to see their effect, mark builds made from uncommitted code, open the installed app at login, show unseen errors in the sidebar, and add a security policy as a second lock on the window's content.

## Plan
1. **Lighter refreshes:** Separate, configurable timers for live stats, battery, and storage, and slower refreshes while the window isn't in front.
2. **Own-usage card:** The app's own CPU and memory on the Settings page, with a 60-second line.
3. **Traceable builds:** Mark builds with uncommitted changes, and add a version bump command.
4. **Open at login:** A switch on the Settings page for the installed app.
5. **Error badge:** A red count on the Logs sidebar entry for unseen errors.
6. **Security policy:** A Content-Security-Policy for the window, and tool scripts loaded as files.
7. **Roadmap:** A ROADMAP.md, starting with the menu bar item.

## Step details

### 1. Lighter refreshes
- **Approach:** The battery is read on its own timer (default 10 s instead of every 2 s), because each read starts a macOS tool. Storage gets a setting (30 s, 1 min, 5 min). "Slow down in the background" (default on) keeps every timer at 10 s or slower while another app is in front; the header shows "(background)". Settings buttons can carry custom labels such as "5 min".
- **Files:** app/tools/system_monitor/__init__.py, app/tools/system_monitor/models.py, app/tools/system_monitor/ui/view.js, app/preferences.py, app/ui/settings.js

### 2. Own-usage card
- **Approach:** Every 2 s while Settings is open: CPU now, CPU average over 60 s, memory, and a sparkline on a fixed 0–10 % scale, on the same whole-CPU scale as Top apps. It includes the WebKit helper processes that draw the window when macOS links them to the app (an undocumented call, also used by Activity Monitor); otherwise it says it counts the app's own code only.
- **Files:** app/app_usage.py, app/bridge.py, app/ui/settings.js, app/ui/style.css
- **Concerns:** The helper link can only be confirmed while the app runs; the card states which case applies.

### 3. Traceable builds
- **Approach:** The stamp records whether tracked files had uncommitted changes (new untracked files don't count) and the label ends in "· modified". make bump_version raises the version with uv (patch by default, PART=minor or major).
- **Files:** app/build_info.py, Makefile

### 4. Open at login
- **Approach:** macOS's SMAppService (macOS 13+, no password). States: On, Off, needs approval (with a pointer to System Settings), unavailable (the dev copy, with a note). Adds the pyobjc ServiceManagement package.
- **Files:** app/login_item.py, app/bridge.py, app/ui/settings.js, pyproject.toml, uv.lock

### 5. Error badge
- **Approach:** A log handler counts ERROR and CRITICAL lines; the shell checks every 5 s (paused while hidden) and shows the unseen count on Logs (a dot when the sidebar is collapsed). Opening Logs marks them seen.
- **Files:** app/logging_setup.py, app/bridge.py, app/ui/shell.js, app/ui/style.css

### 6. Security policy
- **Approach:** Scripts only from the app's own files or in-memory files; no inline code or event attributes; no network or outside images; plugins, base-URL changes and forms off. 'unsafe-eval' stays because pywebview builds its bridge functions from text. Tool scripts load through a blob: URL instead of being pasted into the page. Blocked attempts are written to the log, so they also raise the error badge.
- **Files:** app/ui/index.html, app/ui/shell.js
- **Concerns:** Can only be confirmed in the running app; a broken policy would show as tools not loading and a "Blocked by the security policy" line in Logs.

### 6b. Version in the sidebar and no-jump Settings page (added on review)
- **Approach:** A small, muted "v0.1.0" line under Settings in the sidebar ("· dev" or "· modified" when that applies), with the full stamp on hover, hidden when the sidebar is collapsed. The Settings page jumped on every click because each click rebuilt the whole page; it is now drawn once per visit and clicks only update the buttons that changed, live usage numbers have a fixed width, and the rule is written down in app/ui/README.md ("Pages must never jump").
- **Files:** app/build_info.py, app/bridge.py, app/ui/index.html, app/ui/shell.js, app/ui/settings.js, app/ui/style.css, app/ui/README.md

### 7. Tests
- **Files:** tests/test_app_usage.py, tests/test_app_login_item.py, tests/test_app_logging_setup.py, tests/test_app_csp.py, tests/test_system_monitor_tool.py, tests/test_app_build_info.py, tests/test_app_bridge.py, tests/test_app_preferences.py, tests/conftest.py

## Decisions
- Defaults → battery 10 s, storage 30 s, slow down in background on, live refresh unchanged at 2 s
- Menu bar item → roadmap
- Automatic PR checks → roadmap, not now
- make upgrade → not needed
- Learning notes → keep
