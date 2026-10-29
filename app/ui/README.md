<!-- LEARN-README -->
start here → [index.html](index.html), then follow each file's "read next"

# app/ui/

The shell page: plain HTML, CSS and JavaScript, no build step.

## Pieces

```
index.html
  ├─ style.css     colour tokens, sidebar, cards, shared chart styles
  ├─ icons.js      BaoIcons.svg(name)        inline Lucide icons
  ├─ charts.js     BaoCharts                 ring, arc gauge, sparkline
  ├─ settings.js   BaoSettingsView           Settings page, built from Python
  └─ shell.js      sidebar, tool switching, shortcuts, error forwarding
                     │
                     └─ loads each tool's view.html / view.css / view.js
                        on first open; the tool calls BaoTools.register(...)
```

## Pages must never jump

This bug appeared twice (System Monitor, then Settings). Every page and tool
must follow these rules, and every change to a page is checked against them:

1.  **Draw once, then update in place.** A page is built once per visit.
    Timers and clicks change only what changed: a number's text, a button's
    "on" class, a style. Never rebuild a page or card with innerHTML on a
    timer or a click.
1.  **Keep the scroll position** around any full redraw that can't be
    avoided (settings.js keepScrollPosition, view.js
    renderKeepingScrollPosition).
1.  **Reserve space** for things that arrive later: list rows, notes, loading
    skeletons. Nothing may grow after it appears.
1.  **Fix the width of live numbers** (the num class plus a min-width), so a
    number gaining a digit can't re-wrap the text next to it.
1.  **Keep overflow-anchor: none** on the scrolling area (style.css,
    .content), so the browser never moves the page on its own.

Why it happens: rebuilding empties the page for a moment, so the page gets
shorter and the browser snaps the scroll position. Then it grows back, and
the content has moved under your mouse.

## Tool lifecycle

```
open tool ──▶ mount(container, ctx) ──▶ timers start
hide window ─▶ pause()                ──▶ timers stop
show window ─▶ resume()               ──▶ timers start
switch tool ─▶ unmount()              ──▶ timers stop, listeners removed
```

## Glossary

| Term | One line |
|---|---|
| CSS custom property | A variable like --accent, read with var(--accent) |
| container query | @container rules react to a box's own width, not the window |
| stroke-dashoffset | Shifts a dashed outline; used to fill rings and gauges |
| visibilitychange | Browser event fired when the page is hidden or shown |
| pywebviewready | Event pywebview fires once window.pywebview.api exists |
| tabular-nums | Font setting giving all digits equal width, so numbers do not jitter |
| IIFE | (() => { … })() — runs once, keeps the file's names private |
| window global | window.BaoCharts = … — how these files share code without imports |
| arrow function | (x) => x * 2 — a short way to write a function |
| template string | Text in backticks with ${x} inside, like a Python f-string |
| Promise / await | "Answer comes later"; await pauses until it arrives (every bridge call) |
| innerHTML / textContent | Replace an element's inside with HTML / with plain safe text |
| event listener | addEventListener("click", f) — call f when that happens |
| event delegation | One listener on a parent handles clicks on all its buttons |
| mount / unmount | A view's start / stop hooks, called by shell.js |
