<!-- LEARN:start -->
start here → [Makefile](Makefile) (the commands), then follow each file's
"read next"
<!-- LEARN:end -->

# Bao Internal Apps

Bao Internal Apps is a macOS desktop app that hosts small internal tools
behind a sidebar. It runs from source while you develop it, and installs as a
regular Mac app that you can open from Spotlight, Launchpad, or the Dock.

## Features

*   **System Monitor**: CPU and memory use, CPU and GPU temperature, battery
    and charger power, the apps that use the most CPU and memory, storage on
    every drive, and which Mac this is (model, age, and uptime).
*   **Logs**: the app's own log file, live, with level filters and search.
    A red count on **Logs** in the sidebar shows errors you haven't seen.
*   **Settings**: open the app at login, see how much CPU and memory the app
    itself uses, and change each tool's settings.

## Requirements

*   A Mac with macOS 13 or later. The app is developed on Apple silicon.
*   Python 3.14.8, the version in `.python-version`. The project never
    downloads Python for you, so install it first, for example from
    [python.org](https://www.python.org/downloads/macos/).
*   Git, to clone the repository and to stamp each build with its commit.

You don't need administrator rights or a password. Everything installs into
the project folder, and the app reads system information the same way the
built-in System Information app does.

## Set up the development environment

1.  Clone the repository and go to the project folder:

    ```bash
    git clone https://github.com/nhqb1010/automation.git
    cd automation
    ```

1.  Create a virtual environment and install uv into it:

    ```bash
    python3 -m venv .venv
    .venv/bin/pip install uv
    ```

1.  Install the exact package versions from `uv.lock`:

    ```bash
    make sync
    ```

Nothing is installed outside the `.venv` folder. To start over, delete
`.venv` and repeat these steps.

## Run the app while you develop

```bash
make start_app
```

The window title ends in **(dev)**. This copy runs your code directly, so a
change shows up the next time you start it. If the app is already open,
starting it again brings the open window to the front instead.

## Install the app on your Mac

```bash
make install_app
```

This command does the following:

1.  Builds `dist/Bao Internal Apps.app` from your current code.
1.  Quits the installed app, if it's open. The app saves its window and
    settings as it quits, the same as pressing ⌘Q.
1.  Replaces the app in `~/Applications`.
1.  Opens the new version.

After the first install, press ⌘Space and type **Bao** to open the app.

To check which version is installed, open **Settings** in the app. The line
at the bottom shows the version, the build time, and the Git commit, for
example `Version 0.1.0 · built 29 Oct 22:40 · ff822d1`. If the app was built
while files had uncommitted changes, the line ends in `· modified`.

### Open the app at login

1.  Install the app with `make install_app`.
1.  In the app, open **Settings** and set **Open at login** to **On**.

macOS shows a "Login item added" notice. To turn it off, set the switch back
to **Off**, or use **System Settings > General > Login Items**. The switch is
unavailable in the development copy, because only an installed app can open
at login.

### Raise the version number

Raise the version before you install a release you want to tell apart:

```bash
make bump_version              # 0.1.0 → 0.1.1, for small fixes
make bump_version PART=minor   # 0.1.0 → 0.2.0, for new features
make bump_version PART=major   # 0.1.0 → 1.0.0, for big changes
```

The command updates `pyproject.toml` and `uv.lock`; commit both files.

### Update the installed app

The installed app changes only when you run `make install_app` again.
Pulling or merging new code doesn't update it.

### Remove the installed app

```bash
make uninstall_app
```

Your settings and logs stay in `~/Library`. Delete the folders listed in
[Where the app keeps its data](#where-the-app-keeps-its-data) to remove them
too.

## Where the app keeps its data

The development copy and the installed copy keep separate data, so testing
never changes the installed app. Both copies can be open at the same time.

Development copy (`make start_app`):

*   Settings and window position: `state.json` in the project folder.
*   Logs: `logs/app.log` in the project folder.
*   Developer settings: `.env` in the project folder, if it exists.

Installed copy:

*   Settings and window position:
    `~/Library/Application Support/Bao Internal Apps/state.json`.
*   Logs: `~/Library/Logs/Bao Internal Apps/app.log`.
*   Developer settings: not read. The installed app always uses defaults.

The **Logs** tool always shows the log of the copy you're looking at.

## Keep the app light

System Monitor reads your Mac on timers. To trade freshness for less CPU,
open **Settings** and change these under **System Monitor**:

*   **Refresh interval**: CPU, memory, and temperature (default 2 s).
*   **Battery refresh**: the Power card (default 10 s).
*   **Storage refresh**: drive sizes (default 30 s).
*   **Slow down in the background**: while another app is in front, nothing
    refreshes more often than every 10 s (default on).

The **This app's own usage** card at the top of **Settings** shows the app's
own CPU and memory use. After you change a setting, watch the CPU line for a
minute to see the effect.

## Change developer settings

Developer settings control the default window size, the log level, and the
log folder of the development copy. To change them:

1.  Copy the example file:

    ```bash
    cp example.env .env
    ```

1.  Edit the values you want in `.env`. Each line is explained in
    `example.env`.

The `.env` file is never committed. Settings that users change, such as the
refresh interval, live on the in-app **Settings** page instead.

## Run the tests and checks

```bash
make test   # run the unit tests
make lint   # check code style with Ruff (reports only, changes nothing)
make logs   # follow the development copy's log live; press Ctrl+C to stop
```

The tests use fake system data, so they give the same results on any Mac.

## Add a tool

1.  Create a folder `app/tools/YOUR_TOOL/` with an `__init__.py` file.
1.  In that file, create a class that inherits from `Tool` and sets these
    attributes:
    *   `info`: the tool's ID, name, and sidebar icon.
    *   `actions`: the methods the page is allowed to call.
    *   `ui_dir`: the folder with the tool's page files.
    *   `settings_model` (optional): the tool's settings. They appear on the
        Settings page automatically.
1.  Add `ui/view.html`, `ui/view.css`, and `ui/view.js`. The script
    registers the tool with `window.BaoTools.register("YOUR_TOOL", { mount,
    unmount })` and calls Python through the `call` function it receives.
1.  Add the tool to the list in `app/tools/__init__.py`.

The next `make install_app` includes the new tool automatically.

## Change the app icon

The icon is drawn by `mac_app/make_icon.py`. After you change that script,
redraw the icon and reinstall the app:

```bash
make app_icon
make install_app
```

To see the result first, open `mac_app/icon/preview.png`.

## Troubleshooting

### `make sync` fails because Python 3.14 isn't found

The project never downloads Python. Install Python 3.14.8, then repeat
[Set up the development environment](#set-up-the-development-environment).

### Spotlight doesn't find the installed app

Check that `Bao Internal Apps` is in the **Applications** folder inside your
home folder. Spotlight can take a minute to index a new app.

### The Temperature or Power card is gray

The card shows the reason under its title. A Mac without a battery has no
power information. Temperature sensors can differ between Mac models.

### The Logs entry in the sidebar shows a red number

The number counts errors logged since you last opened the **Logs** tool.
Open **Logs** to read them; the number disappears once you've seen them.

### A line says "Blocked by the security policy"

The app refused to run code that isn't one of its own files, which is what
its security policy is for. If it appears after you changed a page file,
the change loads code in a way the policy doesn't allow. The comment above
the policy in `app/ui/index.html` lists what's allowed.

### The app crashed or a tool didn't load

Open the **Logs** tool, or run `make logs` for the development copy. Errors
from the page are written to the same log as errors from Python.

## Project layout

```
app/                 the app: window, bridge, settings, tools
  ui/                the shell page: sidebar, charts, Settings page
  tools/
    system_monitor/  the System Monitor tool and its page
    log_viewer/      the Logs tool and its page
mac_app/             the Mac app build: recipe, icon, launcher
tests/               unit tests
specs/               the plan and decisions for each feature
mockups/             design mockups (not used by the app)
Makefile             every command in this README
```

Each folder has its own README with more detail.

## Roadmap

Planned ideas that aren't built yet are listed in [ROADMAP.md](ROADMAP.md).

## See also

*   [mac_app/README.md](mac_app/README.md): how the Mac app is built.
*   [app/README.md](app/README.md): how the app starts and how the page
    talks to Python.
*   [tests/README.md](tests/README.md): how the tests are named and run.
*   [specs/](specs/): why each feature works the way it does.

<!-- LEARN:start -->
## How the pieces connect

```
make start_app
   │
   ▼
app/main.py ── creates ──▶ pywebview window ── loads ──▶ app/ui/index.html
   │                                                        │
   ├─ state.json   (window, sidebar, preferences)           │ pywebview.api
   ├─ app.log      (rotating)                               ▼
   └─ AppBridge ◀──────── JSON over the bridge ──── shell.js / view.js
         │
         ├─ tool registry ──▶ SystemMonitorTool ──▶ psutil, SMC, ioreg
         │                ──▶ LogViewerTool     ──▶ app.log (new lines)
         └─ preferences   ──▶ Settings page (from each settings model)
```

*   **pywebview**: a Python library that opens a native window showing a web
    page (WebKit, the engine behind Safari).
*   **bridge**: the Python object whose public methods the page can call.
*   **registry**: the list of tools the sidebar shows.
*   **SMC**: System Management Controller, the chip that reports CPU and GPU
    temperatures.
*   **container query**: CSS that reacts to a box's own width instead of the
    window's width.

## Reading path

Every file starts with a YOU ARE HERE header that ends in "read next →".
Following it from the Makefile walks the whole project:

```
Makefile ▶ app/__main__.py ▶ main ▶ paths ▶ config ▶ build_info
  ▶ app_usage ▶ login_item ▶ logging_setup ▶ single_instance ▶ state
  ▶ tools/__init__ ▶ tools/base
  ▶ system_monitor/__init__ ▶ models ▶ cpu_memory ▶ recent_values
  ▶ temperature ▶ power ▶ mac_info ▶ top_apps ▶ app_icons ▶ storage
  ▶ log_viewer/__init__ ▶ models ▶ reader
  ▶ app/preferences ▶ app/bridge
  ▶ ui/index.html ▶ style.css ▶ icons.js ▶ charts.js ▶ shell.js
  ▶ settings.js
  ▶ system_monitor/ui/view.html ▶ view.css ▶ view.js
  ▶ log_viewer/ui/view.html ▶ view.css ▶ view.js
  ▶ mac_app/bao_internal_apps.spec ▶ launch.py ▶ make_icon.py
  ▶ tests/conftest ▶ one test file per module
  ▶ pyproject.toml ▶ ruff.toml ▶ example.env ▶ .gitignore
  ▶ cspell.json (below)
```

The folder READMEs (app/, app/ui/, app/tools/system_monitor/,
app/tools/log_viewer/, mac_app/, tests/) give the big picture of each folder.
Each one starts with "start here →".

## Files that can't hold comments

**cspell.json** is the end of the reading path.

*   Used by ▶ the Code Spell Checker extension in VS Code.
*   Sets up ▶ the list of extra words it accepts (psutil, pywebview, …).
*   What depends on it ▶ nothing in the app; it only stops false spelling
    warnings.
*   JSON allows no comments, so it's explained here:
    *   "language": "en,en-GB" → both US and UK spellings are fine.
    *   "ignorePaths" → folders and files that are never checked.
    *   "words" → extra words to accept, in A–Z order.

**uv.lock** is written by uv, never by hand. It pins the exact version of
every package, so `make sync` installs the same set on any Mac.
<!-- LEARN:end -->
