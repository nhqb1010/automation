# 003: Power card in System Monitor

- **Status:** implemented, waiting for test run
- **Created:** 2026-10-29

## Requirement
See whether the Mac is charging and how many watts are flowing: from the charger, into or out of the battery, and what the Mac itself uses.

## Plan
1. **Reading battery and charger:** Read the battery's live values from macOS without a password on every System Monitor refresh.
2. **Power card:** A new card with a battery ring, the charging state, the watts flow, a sparkline and battery health.
3. **Tests:** Unit tests with a fake battery entry.

## Step details

### 1. Reading battery and charger
- **Approach:**
  - Ask macOS's hardware listing for the battery entry (the same values System Information shows), as structured data, with a 2 second limit.
  - Battery watts = voltage × current; positive while charging, negative on battery. A negative current that arrives as a huge positive number is corrected.
  - Charger watts: the charger's rating, plus the power coming in right now from Apple's power telemetry (an undocumented value; shown as "—" if a future macOS drops it).
  - Mac watts: on battery, what leaves the battery; plugged in, power coming in minus what goes into the battery.
  - Health = today's full capacity ÷ design capacity; cycle count and battery temperature as reported.
  - The last 60 seconds of Mac watts feed a sparkline, like CPU and RAM.
  - No battery, or the read fails → the card is greyed with the reason; each reason is logged once.
- **Files:** app/tools/system_monitor/power.py, app/tools/system_monitor/models.py, app/tools/system_monitor/__init__.py, ruff.toml

### 2. Power card
- **Approach:**
  - Full width under CPU / Memory / Temperature in the 3-column layout; a normal card next to Temperature in the 2-column layout.
  - Battery ring: green while plugged in; on battery blue, yellow at 20 % or less, red at 10 % or less.
  - Status: Charging with time to full, On battery with time left, Plugged in not charging, or Charged.
  - Flow row: Charger (rating) ▶ Drawing (watts in) ▶ Mac uses, plus Battery (+ charging, − draining). Charger boxes hide when unplugged.
  - Sparkline of Mac power use on a fixed 0–100 W scale; health, cycles and battery temperature on the side.
- **Files:** app/tools/system_monitor/ui/view.html, app/tools/system_monitor/ui/view.css, app/tools/system_monitor/ui/view.js, app/ui/icons.js

### 2b. Colours by charge state (added 2026-10-30)
- **Approach:** One state from Python drives the card's colour, ring label and status line: charging green (pulsing), charged teal, on hold blue (plugged in, macOS holding the charge), on battery grey, low amber (20 % or less), very low red (10 % or less, pulsing). The status text, charging bolt and title icon share the ring colour. A yellow "Low Power Mode" tag shows when macOS Low Power Mode is on. Battery watts turn green while charging. Pulsing stops with Reduce Motion.
- **Files:** app/tools/system_monitor/power.py, app/tools/system_monitor/models.py, app/tools/system_monitor/ui/view.html, app/tools/system_monitor/ui/view.css, app/tools/system_monitor/ui/view.js, app/ui/style.css, tests/test_system_monitor_power.py

### 3. Tests
- **Approach:** Parsing while charging and unplugged, the negative current fix, the "estimating" time value, watts maths, no battery, a failed read, and the sparkline history.
- **Files:** tests/test_system_monitor_power.py, tests/conftest.py

## Decisions
- Where → a card in System Monitor, not a new tool
