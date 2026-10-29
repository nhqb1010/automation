# 002: Logs tool (live app log)

- **Status:** implemented, waiting for test run
- **Created:** 2026-10-29

## Requirement
A second sidebar tool that shows the app's own log (logs/app.log) live inside the app, so problems can be seen without a terminal.

## Plan
1. **Reading the log:** Return only the lines added since the last call, starting with the end of the file on first open, and survive the log rolling over.
2. **Logs page:** A live list with level filters, a search box, follow / pause, and colours for warnings and errors.
3. **Settings:** Refresh interval and how many lines the page keeps, on the Settings page.
4. **Tests:** Unit tests with small log files written into a temporary folder.

## Step details

### 1. Reading the log
- **Approach:**
  - The page holds a bookmark (the file's id and how far it has read) and sends it back with each call; Python keeps no state between calls.
  - First open: only the last 256 KB, with the first cut line dropped. After that: from the bookmark to the end, at most 1 MB per call.
  - A different file id, or a file shorter than the bookmark, means it rolled over or was emptied: read the new file from the top.
  - A half-written last line is held back until it is complete. A single line longer than 1 MB is sent anyway so reading never gets stuck.
  - Each line is split into time, level, source and message. Traceback lines attach to the line above; if they arrive first in a batch, the page joins them to its last line.
  - The tool receives the log file path from the logging setup through the tool registry.
- **Files:** app/tools/log_viewer/__init__.py, app/tools/log_viewer/models.py, app/tools/log_viewer/reader.py, app/tools/__init__.py, app/main.py
- **Concerns:** Lines written to the old file between the last poll and a roll over are not shown (at most about a second's worth). If reading fails, the error is logged, which adds a line to the same log each poll.

### 2. Logs page
- **Approach:**
  - Second in the sidebar (Cmd+2), icon "scroll-text".
  - Level chips All / Info / Warn / Error with live counts (Debug and unparsed lines count as Info, Critical as Error) and a search box that filters as you type; both only hide lines, nothing is re-fetched.
  - Following scrolls to the newest line on every batch. Scrolling up or pressing Pause stops it and shows how many new lines arrived; scrolling to the bottom or Jump to newest resumes.
  - Warnings get a yellow stripe and label, errors a red one; tracebacks show indented under their line. Lines can be selected and copied.
  - Log text is put on the page as plain text only, never as markup.
  - Polling stops while the tool or window is hidden, like System Monitor.
- **Files:** app/tools/log_viewer/ui/view.html, app/tools/log_viewer/ui/view.css, app/tools/log_viewer/ui/view.js, app/ui/icons.js

### 3. Settings
- **Approach:** Refresh interval 1, 2 or 5 s (default 1). Lines kept 500, 1000, 2000 or 5000 (default 2000). Shown automatically on the Settings page.
- **Files:** app/tools/log_viewer/__init__.py

### 4. Tests
- **Approach:** First read, new lines only, half-written line held, roll over, missing file, first read starting mid-line, line limit, line splitting, tracebacks, unknown levels, the read start rules.
- **Files:** tests/test_log_viewer_reader.py

## Decisions
- Which log → only the app's own logs/app.log
- Mockup → not needed
- Delivery → polling every second, same pattern as System Monitor
