<!-- LEARN-README -->
start here → [\_\_init\_\_.py](__init__.py), then follow each file's "read next"

# Logs

The app's own log file (logs/app.log), live inside the app.

## One poll

```
view.js timer (every 1 s, Settings)
  │ call("read_new_log_lines", { cursor, max_lines })
  ▼
LogViewerTool ──▶ reader.read_new_log_lines
                    │ start: last 256 KB (first time) / cursor / 0 (new file)
                    │ read ≤ 1 MB, keep whole lines only
                    │ split: time · level · [source] · message (+ traceback)
                    ▼
view.js ◀── { lines, cursor, file_found } ── keeps the cursor for next time
```

## The bookmark (cursor)

```
app.log  [████████████████████░░░░]
          └── already shown ──┘└new┘
                              ▲ offset
file_id = the file's inode; app.log rolls over at 1 MB → new inode → read from 0
```

Python keeps no state: the page holds the cursor and sends it back.

## On the page

```
[All] [Info] [Warn] [Error]   chip  → hide lines of other groups
🔍 filter                     text  → hide lines that don't contain it
⏸ Pause / ⤓ Jump to newest    scroll up = pause, back to the bottom = follow
```

At most "Lines kept" (Settings) lines stay on the page; the oldest drop off.

## Glossary

| Term | One line |
|---|---|
| tailing | Following the end of a file as it grows (like tail -f) |
| cursor / continuation token | A bookmark the client sends back so the server can stay stateless |
| inode | macOS's id number for one file; a new file at the same path gets a new one |
| log rotation | app.log is renamed to app.log.1 at 1 MB and a fresh app.log starts |
| regular expression | A text pattern; here it splits a line into time, level, source, message |
| auto-scroll / tail mode | The list keeps jumping to the newest line until you scroll up |
| bounded buffer | Keep only the newest N items; the oldest drop off |
| DocumentFragment | An off-page holder for many new elements, added to the page in one go |
