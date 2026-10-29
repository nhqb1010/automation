<!-- LEARN-README -->
start here → [\_\_init\_\_.py](__init__.py), then follow each file's "read next"

# System Monitor

## Where each number comes from

```
CPU %, cores, load  ── psutil.cpu_percent / getloadavg
P / E labels        ── sysctl hw.perflevel0 / perflevel1 (E cores listed first)
RAM, swap           ── psutil.virtual_memory / swap_memory
Top apps            ── psutil.process_iter ──▶ grouped by outermost .app
App icons           ── NSWorkspace.iconForFile (PyObjC) ──▶ 64 px PNG, cached
Temperature         ── SMC keys Tp / Te / Tg (ctypes + IOKit)
                         └─ fallback: IOHID "PMU tdie" sensors ──▶ "Chip"
Battery, charger    ── ioreg AppleSmartBattery (plist, no password)
                         └─ watts = volts × amps; charger watts from telemetry
Model, chip, ages   ── ioreg product-name + system_profiler + setup date
                         └─ read once, kept; uptime from psutil.boot_time
Storage             ── psutil mounts ──▶ NSURL volume values (Finder numbers)
                         └─ each drive read on its own thread, one shared 2 s limit
```

## Data flow per refresh

```
view.js timer
  ├─ get_live_stats ──▶ CpuMemoryReader + TemperatureMonitor + PowerReader ──▶ LiveStats
  ├─ get_top_apps   ──▶ TopAppsReader (only while a list is open) ──▶ TopApps
  ├─ get_storage    ──▶ StorageReader (every 30 s) ──▶ StorageStats
  └─ get_mac_info   ──▶ MacInfoReader (once per visit) ──▶ MacInfo
```

## Glossary

| Term | One line |
|---|---|
| psutil | Cross-platform library for CPU, memory, process and disk numbers |
| priming | First CPU reading is a baseline (0%); real values start from the second |
| P / E cores | Performance and efficiency cores on Apple Silicon |
| SMC | System Management Controller; holds fan, power and temperature keys |
| four character code | A 4-letter key like Tp09 packed into one 32 bit number |
| IOHID | Apple's sensor hub API; the fallback temperature source |
| ctypes | Calls C functions in a system library directly from Python |
| PyObjC | Calls Objective C classes (AppKit, Foundation) from Python |
| purgeable space | Space macOS can free on demand (caches); Finder counts it as free |
| Unix timestamp | Seconds since 1 Jan 1970; how boot time is passed to the page |
| memoization | Keep a value that can't change instead of asking again |
| ioreg | macOS tool that lists hardware entries and their live values |
| two's complement | How negative numbers are stored; ioreg can show them as huge positives |
| rolling window | Keep only the last 60 s of values (recent_values.py) |
| polling | The page asks again on a timer instead of Python pushing updates |
| FLIP animation | Rows slide to their new rank instead of jumping (view.js) |
