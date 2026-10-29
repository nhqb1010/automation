# 005: This Mac card in System Monitor

- **Status:** implemented, waiting for test run
- **Created:** 2026-10-29

## Requirement
Show which Mac this is and how old it is, next to the battery health, so wear can be judged against age.

## Plan
1. **Reading the details:** Model name, chip, memory, macOS version, set-up date and last restart, without a password.
2. **This Mac card:** Name and specs, a timeline from model year to set-up to today, ages, and a live uptime line.
3. **Tests:** Year and month maths, missing values, and reading each source from fake output.

## Step details

### 1. Reading the details
- **Approach:** Model name from macOS's hardware record (the name About This Mac shows); chip and memory from the System Information hardware report; macOS version from Python; set-up date from the date macOS marks its first-start setup as done; last restart from psutil. Asked once and kept, since none of it changes; ages are worked out fresh on each visit. Anything unreadable shows "—".
- **Files:** app/tools/system_monitor/mac_info.py, app/tools/system_monitor/models.py, app/tools/system_monitor/__init__.py, ruff.toml
- **Concerns:** If macOS was installed fresh later, the set-up date is that reinstall, so the card says "set up", not "bought".

### 2. This Mac card
- **Approach:** Wide window: Power takes two thirds of its row and This Mac the last third; two columns: This Mac is a full-width strip; one column: stacked. Timeline dots are placed by date (model year → set up → today). The uptime line updates with every live refresh.
- **Files:** app/tools/system_monitor/ui/view.html, app/tools/system_monitor/ui/view.css, app/tools/system_monitor/ui/view.js, app/ui/icons.js

### 3. Tests
- **Files:** tests/test_system_monitor_mac_info.py
