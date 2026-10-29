# 004: Bao Internal Apps as a real Mac app

- **Status:** implemented, waiting for test run and first install
- **Created:** 2026-10-29

## Requirement
Open the app like any other Mac app (Spotlight, Launchpad, Dock, ⌘Tab with its own name and icon), and deploy the latest code with one command while still developing from source.

## Plan
1. **Build tool:** Package the app as a standalone .app with PyInstaller.
2. **Dev copy vs installed copy:** Separate data, logs and window title so testing never touches the installed app.
3. **Version stamp:** Show the version, build time and commit on the Settings page.
4. **Icon:** Draw an app icon that matches the dark theme.
5. **Make commands:** Build, install (deploy), uninstall, redraw the icon.
6. **Tests:** Location choice and version stamp.

## Step details

### 1. Build tool
- **Approach:** PyInstaller (6.22, supports Python 3.14) as a pinned dev dependency. A build recipe bundles Python, the libraries, every ui folder under app/ (so new tools ship automatically), the version stamp and the icon. Info.plist: name "Bao Internal Apps", id com.nhqb.bao-internal-apps, version from pyproject.toml, category Developer Tools, macOS 13 or newer. About 32 MB.
- **Files:** mac_app/bao_internal_apps.spec, mac_app/launch.py, pyproject.toml, uv.lock
- **Concerns:** Built locally, so no Gatekeeper warning; sharing with other Macs would need Apple signing (out of scope).

### 2. Dev copy vs installed copy
- **Approach:** The app detects whether it is the built app. Installed: data in ~/Library/Application Support/Bao Internal Apps, logs in ~/Library/Logs/Bao Internal Apps, no .env. Dev: project folder as before, title "Bao Internal Apps (dev)". Separate single-copy sockets, so both can run at once. The data folder is created on first start.
- **Files:** app/paths.py, app/config.py, app/main.py

### 3. Version stamp
- **Approach:** The build writes version, build time and git commit into the app. The Settings page footer shows "Version 0.1.0 · built 29 Oct 22:40 · ff822d1", or "Version 0.1.0 · dev · ff822d1" for the dev copy. A missing stamp shows "unknown" instead of failing.
- **Files:** app/build_info.py, app/bridge.py, app/ui/settings.js, app/ui/style.css

### 4. Icon
- **Approach:** Drawn by a script with macOS's own drawing library: dark rounded square, faint sidebar with the first item in blue, glowing blue pulse line. Packed into an .icns with the built-in iconutil. Preview at mac_app/icon/preview.png.
- **Files:** mac_app/make_icon.py, mac_app/icon/AppIcon.icns, mac_app/icon/preview.png

### 5. Make commands
- **Approach:** build_app; install_app = build, quit the installed app by its bundle id (it saves its window like ⌘Q), replace it in ~/Applications, open it; uninstall_app; app_icon.
- **Files:** Makefile, README.md, mac_app/README.md

### 6. Tests
- **Files:** tests/test_app_paths.py, tests/test_app_build_info.py, tests/test_app_bridge.py

## Decisions
- Launcher vs standalone → standalone (option B)
- Icon → drawn by Claude
- Builder → PyInstaller (py2app's latest release only lists Python up to 3.9)
- Folder name → mac_app/ ("packaging" would clash with a Python library PyInstaller uses)
