<!-- LEARN-README -->
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
Storage             ── psutil mounts ──▶ NSURL volume values (Finder numbers)
                         └─ each drive read on its own thread, one shared 2 s limit
```

## Data flow per refresh

```
view.js timer
  ├─ get_live_stats ──▶ CpuMemoryReader + TemperatureMonitor ──▶ LiveStats
  ├─ get_top_apps   ──▶ TopAppsReader (only while a list is open) ──▶ TopApps
  └─ get_storage    ──▶ StorageReader (every 30 s) ──▶ StorageStats
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
