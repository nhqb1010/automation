<!-- LEARN-README -->
start here → [\_\_main\_\_.py](__main__.py), then follow each file's "read next"

# app/

The Python side: window, bridge, settings, state, tools.

## Startup

```
python -m app
  │
  ▼
__main__ ──▶ main.run_internal_apps()
               │
               ├─ config         .env ──▶ AppSettings (BAO_ keys)
               ├─ logging_setup  logs/app.log, rotating, crash hook
               ├─ single_instance  already running? ──▶ focus it, quit
               ├─ state          state.json ──▶ window, ui, preferences
               ├─ tools          registry ──▶ [SystemMonitorTool, LogViewerTool]
               ├─ bridge         the object the page can call
               └─ webview.start  window + macOS event loop (blocks)
```

## A call from the page

```
view.js ── api.call(tool, action, params) ──▶ bridge.call
                                                 │ tool known?  action allowed?
                                                 ▼
                                          tool.action(**params) ──▶ pydantic model
                                                 │
view.js ◀───────────── JSON ◀── model_dump ◀──────┘
```

## Glossary

| Term | One line |
|---|---|
| pywebview | Opens a native macOS window that shows a web page (WebKit, like Safari) |
| js_api | The Python object pywebview exposes to JavaScript as window.pywebview.api |
| main thread | macOS only allows UI work on it; pywebview.start must run there |
| pydantic-settings | pydantic models filled from environment variables and .env |
| atomic write | Write a temp file, then rename it over the old one in one step |
| Unix socket | A file-shaped endpoint for two local processes to talk |
| excepthook | Python hook that runs for any error nobody caught |
| allowlist | Only names on a fixed list may run (the tool's actions) |
| schema-driven UI | The Settings page is drawn from each settings model, no page code per tool |
