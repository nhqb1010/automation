# LEARN: YOU ARE HERE
#   make build_app ▶ PyInstaller reads THIS FILE (the build recipe)
#   ▶ dist/Bao Internal Apps.app ▶ make install_app copies it to ~/Applications
#   read next → mac_app/launch.py
#
# LEARN: a .spec file is plain Python that PyInstaller runs
#   Analysis, PYZ, EXE, COLLECT, BUNDLE are provided by PyInstaller (no import)
#   SPECPATH = the folder this file is in (also provided)
#
#   launch.py ─▶ Analysis   follow every import, list what the app needs
#             ─▶ PYZ        pack the Python code into one archive
#             ─▶ EXE        the small program that starts Python
#             ─▶ COLLECT    put the program + libraries + data in one folder
#             ─▶ BUNDLE     wrap that folder as a Mac .app with an Info.plist
#
# LEARN: inside the finished .app (a .app is just a folder)
#
#   Bao Internal Apps.app/
#   └─ Contents/
#      ├─ Info.plist       name, id, version, icon (macOS reads this)
#      ├─ MacOS/           the program macOS starts
#      ├─ Frameworks/      Python itself + libraries (psutil, pywebview, …)
#      └─ Resources/       AppIcon.icns, the ui folders, build_info.json
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(SPECPATH).parent
APP_NAME = "Bao Internal Apps"
BUNDLE_ID = "com.nhqb.bao-internal-apps"

with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
    VERSION = tomllib.load(pyproject_file)["project"]["version"]

# LEARN: datas = files that aren't Python code but must ship with the app
#   (source on disk, folder inside the app)
#   every "ui" folder under app/ is included → a new tool's page ships
#   automatically; same folder layout → Path(__file__).parent / "ui" still works
UI_FOLDERS = [
    (str(folder), str(folder.relative_to(PROJECT_ROOT)))
    for folder in sorted((PROJECT_ROOT / "app").rglob("ui"))
    if folder.is_dir()
]
DATAS = [
    *UI_FOLDERS,
    # written just before this build by: python -m app.build_info
    (str(PROJECT_ROOT / "build" / "build_info.json"), "app"),
]

analysis = Analysis(
    [str(PROJECT_ROOT / "mac_app" / "launch.py")],
    # pathex → where "import app" is found
    pathex=[str(PROJECT_ROOT)],
    datas=DATAS,
    # the tools are imported normally, so nothing is hidden from Analysis
    hiddenimports=[],
    # not needed by the app → smaller .app
    excludes=["tkinter", "pytest", "ruff", "setuptools"],
)
python_archive = PYZ(analysis.pure)

program = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    # console=False → no Terminal window, a normal windowed app
    console=False,
    # macOS-only option; off → the app gets no file-open arguments
    argv_emulation=False,
)

app_folder = COLLECT(
    program,
    analysis.binaries,
    analysis.datas,
    name=APP_NAME,
)

app = BUNDLE(
    app_folder,
    name=f"{APP_NAME}.app",
    icon=str(PROJECT_ROOT / "mac_app" / "icon" / "AppIcon.icns"),
    bundle_identifier=BUNDLE_ID,
    version=VERSION,
    # LEARN: Info.plist = the .app's ID card, read by macOS
    #   CFBundleShortVersionString → version shown in Finder's Get Info
    #   NSHighResolutionCapable → sharp on Retina screens
    #   LSApplicationCategoryType → its category (Developer Tools)
    #   LSMinimumSystemVersion → oldest macOS it will open on
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.developer-tools",
        "LSMinimumSystemVersion": "13.0",
    },
)
