<!-- LEARN:start -->
start here → [Makefile](Makefile) (the commands), then follow each file's "read next"
<!-- LEARN:end -->

# Bao Internal Apps

A small macOS desktop app that hosts internal tools behind a sidebar.
Tools so far:

- **System Monitor**: CPU, RAM, temperature, top apps and storage.
- **Logs**: the app's own log file, live, with level filters and search.

## Run the app

```bash
make start_app   # open the app window
make test        # run the unit tests
make lint        # Ruff lint + format check
make sync        # install exactly what uv.lock lists
make logs        # follow logs/app.log live
```

Optional developer settings: copy `example.env` to `.env` and change what you need.

## Rebuild the environment

```bash
python3 -m venv .venv
.venv/bin/pip install uv
.venv/bin/uv sync --locked
```

## Add a new tool

1. Create a folder under `app/tools/<your_tool>/` with an `__init__.py`.
2. In it, subclass `Tool`: set `info` (id, name, icon), `actions` (the methods the page may call) and `ui_dir`. Add a `settings_model` if the tool has settings; it appears on the Settings page automatically.
3. Add `ui/view.html`, `ui/view.css` and `ui/view.js`. The script registers itself with `window.BaoTools.register("<id>", { mount, unmount })` and talks to Python through the `call` function it receives.
4. Add the tool to the list in `app/tools/__init__.py`.

<!-- LEARN:start -->
## How the pieces connect

```
make start_app
   │
   ▼
app/main.py ── creates ──▶ pywebview window ── loads ──▶ app/ui/index.html (shell)
   │                                                        │
   ├─ state.json   (window, sidebar, preferences)           │ window.pywebview.api
   ├─ logs/app.log (rotating)                               ▼
   └─ AppBridge ◀──────────── JSON over the bridge ──── shell.js / tool view.js
         │
         ├─ tool registry ──▶ SystemMonitorTool ──▶ psutil, SMC, macOS volumes
         │                ──▶ LogViewerTool     ──▶ logs/app.log (new lines only)
         └─ preferences   ──▶ Settings page (built from each tool's settings model)
```

| Term | Meaning |
|---|---|
| pywebview | Python library that opens a native window showing a web page (WebKit) |
| bridge | The Python object whose public methods the page can call |
| registry | The list of tools the hub shows |
| SMC | System Management Controller: the chip that reports CPU / GPU temperatures |
| container query | CSS that reacts to a box's own width instead of the window's |

## Reading path

Every file starts with a YOU ARE HERE header that ends in "read next →".
Following it from the Makefile walks the whole project:

```
Makefile ▶ app/__main__.py ▶ main ▶ paths ▶ config ▶ logging_setup
  ▶ single_instance ▶ state ▶ tools/__init__ ▶ tools/base
  ▶ system_monitor/__init__ ▶ models ▶ cpu_memory ▶ recent_values
  ▶ temperature ▶ top_apps ▶ app_icons ▶ storage
  ▶ log_viewer/__init__ ▶ models ▶ reader
  ▶ app/preferences ▶ app/bridge
  ▶ ui/index.html ▶ style.css ▶ icons.js ▶ charts.js ▶ shell.js ▶ settings.js
  ▶ system_monitor/ui/view.html ▶ view.css ▶ view.js
  ▶ log_viewer/ui/view.html ▶ view.css ▶ view.js
  ▶ tests/conftest ▶ one test file per module
  ▶ pyproject.toml ▶ ruff.toml ▶ example.env ▶ .gitignore ▶ cspell.json (below)
```

Folder READMEs (app/, app/ui/, app/tools/system_monitor/, app/tools/log_viewer/,
tests/) give the
big picture of each folder; each starts with "start here →".

## Files that cannot hold comments

**cspell.json** — the end of the reading path.

- used by ▶ the Code Spell Checker extension in VS Code
- sets up ▶ the list of words it should accept (psutil, pywebview, …)
- what depends on it ▶ nothing in the app; it only stops false spelling warnings
- JSON allows no comments, so it is explained here:
  - "language": "en,en-GB" → both US and UK spellings are fine
  - "ignorePaths" → folders / files never checked (venv, logs, lock file)
  - "words" → extra words to accept, in A–Z order

**uv.lock** — written by uv, never by hand. It pins the exact version of
every package, so make sync installs the same set on any Mac.
<!-- LEARN:end -->
