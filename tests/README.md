<!-- LEARN-README -->
start here → [conftest.py](conftest.py), then follow each file's "read next"

# tests/

Unit tests for the Python side. Run them with `make test`.

## How a test run works

```
make test ──▶ pytest
                │ finds every tests/test_*.py
                │ loads conftest.py first (shared fakes)
                ▼
            class Test…  ──▶ each method test_…  ──▶ asserts
                                  ▲
                                  └─ asks for fixtures by name
                                     (fake_clock, state_store, tmp_path, …)
```

## Names (so one command picks a group)

```
file   test_system_monitor_storage.py
class  TestSystemMonitorStorage<Function>     same start in the whole file
method test_system_monitor_storage_<detail>

pytest -k "SystemMonitor"            every System Monitor test
pytest -k "TestSystemMonitorStorage" one file
```

## What is faked

The tests never touch the real Mac: clock, processes, sensors and drives are
replaced with fakes, so results are the same everywhere and nothing waits.

## Glossary

| Term | One line |
|---|---|
| fixture | A ready-made input a test asks for by naming it as a parameter |
| conftest.py | pytest's shared file; its fixtures work in every test file |
| tmp_path | Built-in fixture: a fresh empty folder for one test |
| monkeypatch | Built-in fixture: swap a function or env var for one test only |
| caplog | Built-in fixture: catches log lines so a test can check them |
| pytest.raises | Passes only if the code inside raises that error |
| fake / test double | A stand-in for the real thing (clock, sensors) |
| pure function | Numbers in, result out, nothing else touched — easy to test |
