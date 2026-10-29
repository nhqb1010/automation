<!-- LEARN-README -->
start here → [bao_internal_apps.spec](bao_internal_apps.spec), then follow each file's "read next"

# mac_app/

Turns the project into a real Mac app: `Bao Internal Apps.app` in
~/Applications, found by Spotlight and Launchpad, with its own Dock icon.

## Everyday use

```
make start_app      develop: runs your code directly, title says "(dev)"
make install_app    deploy: build → quit the installed app → replace it → open it
make uninstall_app  remove it from ~/Applications (settings and logs stay)
make build_app      build only → dist/Bao Internal Apps.app
make app_icon       redraw the icon after changing make_icon.py
```

The installed app changes only when you run `make install_app`;
merging or pulling code does not update it.

## How a build works

```
make build_app
  │
  ├─ python -m app.build_info build/build_info.json   version · time · commit
  │
  └─ pyinstaller bao_internal_apps.spec
       launch.py ─▶ follow imports ─▶ pack Python + libraries + ui folders
                                       + build_info.json + AppIcon.icns
                                   ─▶ dist/Bao Internal Apps.app
```

## Dev copy vs installed copy

```
                     make start_app (dev)       installed .app
settings / state     project folder             ~/Library/Application Support/Bao Internal Apps/
logs (Logs tool)     logs/                      ~/Library/Logs/Bao Internal Apps/
.env                 read                       ignored
window title         Bao Internal Apps (dev)    Bao Internal Apps
```

Both can be open at the same time; each has its own single-copy check.

## Files

| File | What it is |
|---|---|
| bao_internal_apps.spec | PyInstaller's build recipe (plain Python) |
| launch.py | The first code the built app runs; calls app/main.py |
| make_icon.py | Draws the icon with macOS's drawing library |
| icon/AppIcon.icns | The icon at every size (made by make_icon.py) |
| icon/preview.png | The icon at 1024 px, to look at |

## Glossary

| Term | One line |
|---|---|
| .app bundle | A folder macOS shows as one app: Contents/ with Info.plist, MacOS/, Resources/ |
| Info.plist | The app's ID card: name, bundle id, version, icon, category |
| bundle id | A unique reverse-domain name for the app (com.nhqb.bao-internal-apps) |
| PyInstaller | Packs Python, the code and its libraries into one standalone app |
| frozen app | Python + code packed into one program; sys.frozen is True inside it |
| .icns | Apple's icon file: the same picture at 16 to 1024 px |
| ad-hoc signing | A local signature PyInstaller adds so Apple Silicon will run the app |
| ditto | macOS's copy tool that keeps everything a .app needs intact |
