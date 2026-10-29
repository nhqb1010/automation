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
