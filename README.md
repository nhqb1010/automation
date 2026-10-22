# Bao Internal Apps

A small macOS desktop app that hosts internal tools behind a sidebar.
The first tool is **System Monitor**: CPU, RAM, temperature, top apps and storage.

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
         └─ preferences   ──▶ Settings page (built from each tool's settings model)
```

| Term | Meaning |
|---|---|
| pywebview | Python library that opens a native window showing a web page (WebKit) |
| bridge | The Python object whose public methods the page can call |
| registry | The list of tools the hub shows |
| SMC | System Management Controller: the chip that reports CPU / GPU temperatures |
| container query | CSS that reacts to a box's own width instead of the window's |
<!-- LEARN:end -->
