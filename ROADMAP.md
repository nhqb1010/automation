# Roadmap

Ideas for Bao Internal Apps that are planned but not built yet. Each one gets
a spec in `specs/` when work on it starts.

## Menu bar item

Show live numbers in the macOS menu bar, next to the Wi-Fi and battery icons,
so you can check them without opening the window.

*   The menu bar shows a short reading, for example `▲ 18% · ⚡86%`.
*   Clicking it opens a menu with CPU, memory, and battery, plus **Open Bao
    Internal Apps** and **Quit**.
*   Open question: when you close the window, does the app keep running in
    the menu bar or quit? Most menu bar apps keep running.

## Automatic checks on pull requests

Run `make lint` and `make test` on every pull request with GitHub Actions on
a macOS runner, and check that `make build_app` still produces a complete
app. Postponed for now.
