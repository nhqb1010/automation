# 001: Bao Internal Apps shell + System Monitor tool

- **Status:** done
- **Created:** 2026-10-22

## Requirement
A lightweight desktop app (pywebview window, no browser) that hosts many internal tools behind a sidebar. The first tool is System Monitor: CPU and RAM usage, CPU/GPU temperature, which apps use the most CPU and RAM, and how much of each drive is used. Visual first (rings, gauges, sparklines, donuts), always dark.

## Plan
1. **App shell:** Window with a collapsible sidebar of tools and a content area. Tools plug in through a registry; window size, position and UI state are remembered.
2. **App settings:** Developer settings come from .env; user preferences are edited on an in-app Settings page with one section per tool and saved to a local JSON file.
3. **CPU and RAM usage:** Read total and per-core CPU (with P/E labels), load average, RAM and swap, plus a short in-memory history for sparklines.
4. **Top apps by CPU and RAM:** List the heaviest apps, with helper processes grouped under their parent app, shown with icons, bars (rings when narrow) and sparklines.
5. **CPU and GPU temperature:** Read CPU and GPU temperatures from the SMC chip without a password, fall back to a whole-chip reading, and degrade to a greyed "unavailable" card if both fail.
6. **Storage usage:** Show every drive as a donut, with the main disk most prominent and network drives and disk images in a muted style.
7. **System Monitor page:** The responsive card layout, shared chart components and live refresh, as in mockups/system_monitor.html.
8. **Tests:** Unit tests with fake system data so results are predictable on any machine.
9. **Run instructions:** Makefile commands and README sections for running, rebuilding and adding a tool.
10. **Repo tooling:** Keep lint, type-check and spell-check settings in repo config files instead of inline comments in the code (added after implementation).

## Step details

### 1. App shell
- **Approach:**
  - pywebview opens one window titled "Bao Internal Apps", loading the shell page through pywebview's built-in local file serving (no separate server).
  - A single bridge object is exposed to the page with one gateway, call(tool, action, params); it only runs actions the tool explicitly lists and rejects anything else.
  - Each tool provides info (id, name, icon), a backend class with its actions, its settings model and its page files; the shell builds the sidebar from the registry.
  - Window: 1000 x 680 centered on first launch, resizable, minimum 720 x 480. Size and position are saved on close and restored on launch only if still on a connected screen; otherwise centered default.
  - Sidebar is about 200 px wide and collapses to icons only; the collapsed state and the last open tool are remembered.
  - Keyboard shortcuts: Cmd+1..9 switch tools, Cmd+, opens Settings, Cmd+\ toggles the sidebar.
  - Single instance: launching while already open brings the existing window forward. The running app listens on a Unix socket (.instance.sock in the project folder, removed on exit); a second launch connects, asks it to focus, and quits.
  - Always dark theme; shared colour tokens in one stylesheet. Icons are inline Lucide SVGs (no network).
  - Logging: Python logging, one named logger per module, f-string messages. Log file at logs/app.log (folder configurable in .env), rotated at 1 MB, 3 backups kept. JavaScript errors are forwarded through the bridge into the same log. Uncaught crashes write the traceback before exiting. Routine refreshes are not logged; secrets and process command lines are never logged.
  - Per-tool error card if a tool fails to load; loading skeletons before first data.
- **Files:** app/__main__.py, app/main.py, app/paths.py, app/bridge.py, app/state.py, app/logging_setup.py, app/single_instance.py, app/tools/__init__.py, app/tools/base.py, app/ui/index.html, app/ui/shell.js, app/ui/style.css, app/ui/icons.js
- **Concerns:** pywebview must own the main thread on macOS; a monitor unplugged since last run is caught by the on-screen check; a crash skips saving window state for that run (harmless). When launched from source the Dock shows a generic Python icon and name, fixed only by later .app packaging.
- **Decisions:**
  - Window title → "Bao Internal Apps"
  - Icons → built-in inline Lucide SVG set
  - Remember size/position → yes
  - Collapsible sidebar → yes
  - Theme → always dark
  - Remember last tool, shortcuts, single instance, log file, error card, loading skeleton → all yes
  - Log location → project logs/ folder, configurable in .env; 1 MB x 3 rotation

### 2. App settings
- **Approach:**
  - Developer settings: a pydantic-settings class read from .env with prefix BAO_ (default window size, minimum window size, log level, log folder). example.env is committed with defaults.
  - User preferences: a pydantic model with one section per tool. System Monitor: refresh interval (1, 2, 5, 10 s; default 2), top apps count (3, 5, 10; default 5), top apps lists open or closed.
  - The Settings page (gear at the bottom of the sidebar) is generated from each tool's settings model; fixed choices render as segmented controls. Changes are saved immediately; the Settings page replaces the tool's view, and the tool reads fresh preferences when it is opened again. One "Reset to defaults" per tool section.
  - Preferences, window state and UI state share one state.json in the project folder (gitignored). Written atomically (temp file then rename). An unreadable file is renamed to state.json.bad, defaults are used and a warning is logged. An invalid single value falls back to that field's default only.
- **Files:** app/config.py, app/preferences.py, app/tools/base.py, app/ui/settings.js, app/ui/style.css, example.env
- **Concerns:** state.json in the project folder is lost if the folder is deleted (accepted for now).
- **Decisions:**
  - Interval and top apps count user-editable in app → yes, Settings page with gear icon
  - Settings layout → one section per tool
  - .env prefix → BAO_
  - state.json location → project folder for now
  - Database → none; JSON for now, database choice deliberately deferred

### 3. CPU and RAM usage
- **Approach:** psutil for total and per-core CPU % (primed at start since the first read is 0), load average, RAM total/used/available/% and swap. P/E core counts read from macOS (this machine: 6 Performance, 2 Efficiency) and labelled per core column. A rolling buffer keeps about 60 seconds of CPU % and RAM % in memory. Pydantic models describe everything sent to the page.
- **Files:** app/tools/system_monitor/__init__.py, app/tools/system_monitor/cpu_memory.py, app/tools/system_monitor/history.py, app/tools/system_monitor/models.py
- **Concerns:** Efficiency cores are listed first (cores 0-1), verified on this machine through each core's cluster type in the macOS device tree; if the counts do not add up on another Mac, cores get neutral labels instead. RAM % will be close to but not identical to Activity Monitor.
- **Decisions:**
  - P/E labels → yes
  - History while on another tool → accept the gap; no background sampling
  - Default refresh → 2 seconds

### 4. Top apps by CPU and RAM
- **Approach:** psutil process scan with process objects kept between refreshes (per-process CPU needs two reads). Each process is grouped under the outermost .app folder in its path; CPU and RAM summed per app; processes outside any .app keep their own name. No child rows. App icons fetched once via macOS's icon API (PyObjC), drawn into a 64 px bitmap (about 10 KB each instead of nearly 1 MB at full size) and cached. Per-app rolling history for sparklines, pruned when an app leaves the top N. The scan runs only while the list is expanded. CPU is shown as a share of the whole CPU (0-100%).
- **Files:** app/tools/system_monitor/top_apps.py, app/tools/system_monitor/app_icons.py, app/tools/system_monitor/models.py, app/tools/system_monitor/history.py
- **Concerns:** some system processes (e.g. kernel_task, WindowServer) refuse access without admin rights and are skipped quietly; RAM per app differs slightly from Activity Monitor; apps closing mid-read are skipped.
- **Decisions:**
  - Group by app, no child rows → yes
  - Lists collapsed by default, open/closed state remembered → yes
  - Row visual → app icon, horizontal bar, number, sparkline; bar switches to a small ring when the card is narrow
  - CPU scale → share of whole CPU
  - Scan only while expanded → yes

### 5. CPU and GPU temperature
- **Approach:** two sources, tried in order, both through ctypes with no install and no password.
  - Primary: the SMC chip (AppleSMC driver). On start, list all SMC keys and keep the float temperature keys starting with Tp / Te (CPU) and Tg (GPU). CPU gauge shows the hottest CPU key with the average as small text; GPU gauge shows the hottest GPU key. Key prefixes come from community documentation (Stats, Asahi Linux).
  - Fallback: the IOHID sensor hub. Its "PMU tdie" die sensors give one whole-chip reading, shown as a single "Chip" gauge when the SMC read fails or finds no CPU keys.
  - Readings outside 10-130°C are ignored. Same rolling history as step 3 for the sparkline. All risky code lives in one module.
- **Files:** app/tools/system_monitor/temperature.py, app/tools/system_monitor/models.py
- **Concerns:** both APIs are undocumented and may break with a macOS update; SMC key names differ between chips, so matching is by prefix rather than per-chip lists; Core Foundation objects must be released to avoid a leak every refresh (verified flat over 2,000 reads); SMC key discovery adds about 0.4 s at startup.
- **Decisions:**
  - Method → SMC for a real CPU/GPU split, with the IOHID "Chip" reading as fallback (changed during implementation: on this macOS the IOHID sensors are not named by CPU or GPU)
  - Units → °C only
  - When unavailable → greyed card with a short reason, reason logged once

### 6. Storage usage
- **Approach:** volume info from macOS (PyObjC, Finder's source) for name, internal/external/network/disk-image kind and capacity. The main disk is read through the root volume, which reports the shared storage pool under the name "Macintosh HD" (same numbers as the Data volume and Finder). Hidden system volumes are skipped: only the root volume and drives directly under /Volumes count, and names starting with "." or "com.apple." (Time Machine snapshots and backups) are skipped. Free space uses Finder's "available" figure (counts purgeable space). Each drive is read on its own background thread (daemon, so a stuck read never blocks quitting), at most one read per drive at a time, and all drives share one ~2 second deadline per refresh. A drive that does not answer shows "Not responding"; problems are logged once per drive, plus once when it recovers. Storage refreshes every 30 seconds, only while the tool is visible, and never blocks the CPU/RAM refresh.
- **Files:** app/tools/system_monitor/storage.py, app/tools/system_monitor/models.py
- **Concerns:** used + free may not equal total because of purgeable space; the donut uses Finder's numbers consistently. Sleeping external disks can respond slowly.
- **Decisions:**
  - Time Machine and other system mounts under /Volumes → skipped
  - Show disk images and network drives → yes, in a muted outlined style with a tag
  - Hierarchy → Macintosh HD largest and first; external drives medium in full colour; network drives and disk images small and muted

### 7. System Monitor page
- **Approach:** cards in a CSS grid with container queries: 3 columns wide, 2 medium, 1 narrow. CPU card (ring, sparkline, per-core columns with P/E, top apps), RAM card (ring, sparkline, used/total, swap, top apps), Temperature card (two arc gauges, one sparkline with a CPU line and a GPU line plus a legend; a single line in the Chip fallback), full-width Storage strip (donuts). Hand-drawn SVG charts in a shared chart module for all tools. Values animate with CSS transitions (off under Reduce motion). Polling via a timer calling the bridge at the user's interval; storage on its own 30 s timer; timers stop when the tool is hidden or the window minimized and restart on return. System font with tabular digits. Numbers always shown next to colour. Follow the dataviz guidelines for colours and marks. Reference look: mockups/system_monitor.html.
  - Colour thresholds: CPU and RAM green < 60%, amber 60-85%, red > 85%; temperature green < 70°C, amber 70-90°C, red > 90°C; storage green < 75%, amber 75-90%, red > 90%.
  - Sparkline scale fixed: 0-100% for CPU/RAM, 30-100°C for temperature.
- **Files:** app/tools/system_monitor/ui/view.html, app/tools/system_monitor/ui/view.js, app/tools/system_monitor/ui/view.css, app/ui/charts.js, app/ui/style.css
- **Concerns:** redraws every 1-2 s are light for SVG (values only, not the whole page); green/amber/red is not colour-blind safe on its own, so values are always printed.
- **Decisions:**
  - UI language → plain JavaScript, no TypeScript and no type checking for now
  - Design → mockup approved as is
  - Colour thresholds and fixed sparkline scale → as above

### 8. Tests
- **Approach:** each data module is split into a thin "read from macOS" part and a pure "shape and calculate" part; tests feed fake raw data into the calculating part. Shared fakes in tests/conftest.py (psutil results, process list with Chrome helpers, a vanishing process and an access-denied process, sensor readings including junk values, drives of every kind including an unresponsive network drive). Settings and state tests use pytest's temporary folder. Bridge tested with a dummy tool. pywebview is imported only by app/main.py, which no test imports, so tests never open a window.
  - Covered: CPU/RAM maths and P/E labels; app grouping, sorting, top-N, vanished processes; temperature name sorting, junk filtering and unavailable fallback; storage filtering, kinds and % maths; preferences save/load, invalid values, corrupted file; window state off-screen fallback; bridge rejects unknown tools and actions; .env settings.
- **Files:** tests/conftest.py, tests/test_system_monitor_cpu_memory.py, tests/test_system_monitor_history.py, tests/test_system_monitor_top_apps.py, tests/test_system_monitor_temperature.py, tests/test_system_monitor_storage.py, tests/test_app_preferences.py, tests/test_app_state.py, tests/test_app_config.py, tests/test_app_bridge.py (named per the unit test naming rules: one shared class prefix per file); ruff.toml allows assert and literal values in tests
- **Concerns:** fakes can drift from real macOS/psutil data; accepted, since a broken temperature read is visible in the app and the log.
- **Decisions:**
  - Live tests against real hardware → no, overkill
  - Who runs the tests → the user (make test); Claude writes them but does not run them

### 9. Run instructions
- **Approach:** Makefile with start_app (.venv/bin/python -m app), test (.venv/bin/python -m pytest), lint (ruff check and ruff format --check), sync (.venv/bin/uv sync --locked), logs (tail -f logs/app.log, with a friendly message if no log exists yet). README gains "Run the app" and "Add a new tool" sections next to the existing "Rebuild the environment". .gitignore gains state.json, state.json.bad, logs/ and .instance.sock.
  - Learning material (/learn-task): READMEs with diagrams and glossaries in app/, app/ui/ and app/tools/system_monitor/ (marked LEARN-README), a "How the pieces connect" block in the main README (between LEARN markers), and LEARN: comments in the code. TRIM LEARN or REMOVE LEARN cleans them up later.
- **Files:** Makefile, README.md, .gitignore, example.env, app/README.md, app/ui/README.md, app/tools/system_monitor/README.md
- **Concerns:** none significant.
- **Decisions:**
  - Commands → make start_app, make test, make lint, make sync, make logs
  - Makefile calls .venv directly, not uv run
  - mockups/ folder → committed as design reference

### 10. Repo tooling
- **Approach:** no lint or type-check suppression comments in the code; everything lives in repo config.
  - Pylance: [tool.pyright] typeCheckingMode = "off" in pyproject.toml. Autocomplete and hover docs still work; type-check errors (including the false alarms on PyObjC names, which PyObjC creates at runtime) are not shown.
  - Ruff: imports that sat inside functions moved to the top of their files, so no import-position exceptions are needed. ruff.toml per-file ignores: S603 for cpu_memory.py and storage.py (they only call fixed macOS tools, sysctl and hdiutil, never user input), E501 for app_icons.py (Apple method names exceed the line limit), S101 and PLR2004 for tests.
  - Spell checking: cspell.json at the repo root lists the project's technical words and skips .venv, logs, uv.lock and state.json, for the Code Spell Checker extension.
- **Files:** pyproject.toml, ruff.toml, cspell.json, app/main.py, app/tools/__init__.py, app/tools/system_monitor/app_icons.py, app/tools/system_monitor/storage.py, app/tools/system_monitor/cpu_memory.py
- **Concerns:** with type checking off, real type mistakes are no longer flagged in the editor (matches the current rule that type checkers are not used yet). The cspell word list was built without running cspell, so a few words may still need adding.
- **Decisions:**
  - Suppressions → repo config only, zero noqa / pyright comments in code
  - Pylance type checking → off for this repo only (user setting unchanged)
  - S603 / E501 → per file, not project-wide
  - cspell.json → yes

### Code review fixes (after implementation)
- Switching views quickly: the shell checks after every wait that the view is still the current one before drawing it, and only shows a tool's error card if that tool is still on screen. The System Monitor stops mounting if it was unmounted meanwhile, and the Settings page ignores a load that finishes after it was left.
- System names (process, app and drive names) are escaped before they go into the page, through a shared escape helper in the chart module.
- Storage: Time Machine snapshot mounts skipped; hung drives no longer flood the log, block other drives, or keep the app from quitting (details in step 6).
- Temperature sparkline now draws the GPU history too.
- Refresh calls carry a session number, so a reply from a previous visit neither draws on the new page nor delays its first refresh.
- Memory maths shared between the live history and the stats (no duplicate calculation).
- Second review: refresh timers only start once mount has finished and never while the window is hidden; the Top apps toggle stops if the tool was left while saving; the two-line sparkline has a screen-reader label and draws a shorter line right-aligned on the shared time axis.
- Third review (UI jumping on refresh): top apps rows are built once per app and updated in place, so bars, rings and numbers animate; rows slide to their new place only when the ranking changes and fade in when new; an open list reserves room for all its rows; per-app sparklines use a fixed scale (whole CPU, or all of RAM). Sparklines have a fixed number of slots (60 s of history divided by the refresh interval), so points stay evenly spaced and a filling history grows in from the right. Storage donuts are updated in place and rebuilt only when drives are added or removed, and drive text keeps a minimum width so the row does not rewrap. Once a GPU reading has been seen the second gauge stays, showing a dash when a reading is missed. The whole page still shifted on refresh when scrolled to the bottom: browser scroll anchoring is turned off for the content area, and each redraw puts the scroll position back if it moved, logging the first correction per part so the cause can be traced.
- Tests added: mount point filtering, many hung shares, hung drive logged once, used memory never negative.
- **Files:** app/ui/shell.js, app/ui/settings.js, app/ui/charts.js, app/ui/style.css, app/tools/system_monitor/ui/view.js, app/tools/system_monitor/ui/view.html, app/tools/system_monitor/ui/view.css, app/tools/system_monitor/storage.py, app/tools/system_monitor/cpu_memory.py, tests/conftest.py, tests/test_system_monitor_storage.py, tests/test_system_monitor_cpu_memory.py

## Out of scope
- Menu-bar icon (rumps)
- Packaging as a .app, Dock icon and name, start at login
- Database (deferred; JSON state only)
- Temperature or disk-space alerts and notifications
- Network, battery and uptime stats
- Background sampling while the tool is hidden
- Live tests against real hardware
- TypeScript or JS type checking
- Python type checking (mypy, pyright; Pylance checking is off for this repo)
- Pre-commit hooks, CI, coverage
- Any second tool
