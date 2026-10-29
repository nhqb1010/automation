# LEARN: YOU ARE HERE
#   make app_icon ▶ THIS FILE draws the app icon with macOS's own drawing
#   library ▶ mac_app/icon/AppIcon.icns (+ a preview PNG)
#   ▶ the build puts the .icns inside the .app (Dock, Spotlight, Finder)
#   read next → tests/conftest.py
"""
Draws the app icon: a dark rounded square, a faint sidebar, a glowing pulse line.

LEARN: what a Mac icon file is

  AppIcon.icns = one file holding the same picture at many sizes
    16, 32, 128, 256, 512 px, each also at 2× for Retina screens
  macOS picks the size it needs (tiny in Finder lists, big in Launchpad)

  this script:  draw each size ──▶ AppIcon.iconset/ folder of PNGs
                iconutil -c icns ──▶ AppIcon.icns   (iconutil comes with macOS)

LEARN: the drawing is done on a 1024 × 1024 "design canvas", then scaled
  Apple's icon grid: the rounded square is 824 px with 100 px around it
  (room for the soft shadow), corners ≈ 185 px
  AppKit's y axis points UP (0 = bottom), unlike the web (0 = top)
"""

import shutil
import subprocess
from pathlib import Path

# LEARN: AppKit = Apple's drawing / window library, through PyObjC
#   (already installed with pywebview; see app_icons.py for how names map)
from AppKit import (
    NSBezierPath,
    NSBitmapImageRep,
    NSColor,
    NSCompositingOperationSourceOver,
    NSGradient,
    NSGraphicsContext,
    NSPNGFileType,
    NSShadow,
)
from Foundation import NSAffineTransform, NSMakeRect, NSMakeSize, NSPoint

ICON_DIR = Path(__file__).parent / "icon"
ICONSET_DIR = ICON_DIR / "AppIcon.iconset"
ICNS_FILE = ICON_DIR / "AppIcon.icns"
PREVIEW_FILE = ICON_DIR / "preview.png"
ICONUTIL_PATH = "/usr/bin/iconutil"
DESIGN_SIZE = 1024
# (file name, pixel size) pairs iconutil expects in an .iconset folder
ICONSET_SIZES = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]

# the app's own colours (app/ui/style.css)
ACCENT = (0x39, 0x87, 0xE5)
# the sidebar's "activity" icon (Lucide), as points on a 24 × 24 grid,
# y pointing DOWN like the web; flipped when drawn
PULSE_POINTS = [(2, 12), (6, 12), (9, 3), (15, 21), (18, 12), (22, 12)]


def make_color(red: int, green: int, blue: int, alpha: float = 1.0) -> NSColor:
    # 0–255 numbers → AppKit's 0–1 colour (sRGB, the web's colour space)
    return NSColor.colorWithSRGBRed_green_blue_alpha_(
        red / 255, green / 255, blue / 255, alpha
    )


def draw_icon_background() -> None:
    """
    LEARN: the rounded square with a soft drop shadow and a dark gradient
    called by → draw_app_icon
    """
    tile = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(100, 100, 824, 824), 185, 185
    )
    # LEARN: NSShadow → everything drawn while it's "set" gets this shadow
    #   saveGraphicsState / restoreGraphicsState → undo the shadow after
    NSGraphicsContext.saveGraphicsState()
    shadow = NSShadow.alloc().init()
    shadow.setShadowOffset_(NSMakeSize(0, -12))
    shadow.setShadowBlurRadius_(28)
    shadow.setShadowColor_(make_color(0, 0, 0, 0.45))
    shadow.set()
    make_color(0x12, 0x12, 0x11).setFill()
    tile.fill()
    NSGraphicsContext.restoreGraphicsState()

    # top a little lighter than the bottom; angle 90 → bottom-to-top
    gradient = NSGradient.alloc().initWithStartingColor_endingColor_(
        make_color(0x14, 0x14, 0x13), make_color(0x2A, 0x2A, 0x27)
    )
    gradient.drawInBezierPath_angle_(tile, 90)
    # a thin light rim, like the app's card borders
    make_color(0xFF, 0xFF, 0xFF, 0.08).setStroke()
    tile.setLineWidth_(4)
    tile.stroke()


def draw_sidebar_hint() -> None:
    """
    LEARN: a faint sidebar with three menu dots, echoing the app's layout
    called by → draw_app_icon
    """
    sidebar = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(160, 160, 170, 704), 48, 48
    )
    make_color(0xFF, 0xFF, 0xFF, 0.05).setFill()
    sidebar.fill()
    for index, y in enumerate((760, 690, 620)):
        # first dot = the "selected" tool → accent colour
        alpha = 0.9 if index == 0 else 0.22
        color = (
            make_color(*ACCENT, alpha)
            if index == 0
            else make_color(0xFF, 0xFF, 0xFF, alpha)
        )
        color.setFill()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(200, y, 90, 26), 13, 13
        ).fill()


def build_pulse_path() -> NSBezierPath:
    """
    LEARN: the pulse line, mapped from the 24-grid into the right-hand area

      24-grid x 2..22  → canvas x 380..860
      24-grid y 3..21  → canvas y 720..300 (flipped: AppKit y points up)
    """
    path = NSBezierPath.bezierPath()
    for index, (grid_x, grid_y) in enumerate(PULSE_POINTS):
        x = 380 + (grid_x - 2) / 20 * 480
        y = 720 - (grid_y - 3) / 18 * 420
        point = NSPoint(x, y)
        if index == 0:
            path.moveToPoint_(point)
        else:
            path.lineToPoint_(point)

    path.setLineWidth_(46)
    # NSLineCapStyle 1 = round ends; NSLineJoinStyle 1 = round corners
    path.setLineCapStyle_(1)
    path.setLineJoinStyle_(1)
    return path


def draw_pulse_line() -> None:
    """
    LEARN: the blue pulse with a glow (a blurred blue shadow under it)
    called by → draw_app_icon
    """
    pulse = build_pulse_path()
    NSGraphicsContext.saveGraphicsState()
    glow = NSShadow.alloc().init()
    glow.setShadowOffset_(NSMakeSize(0, 0))
    glow.setShadowBlurRadius_(60)
    glow.setShadowColor_(make_color(*ACCENT, 0.9))
    glow.set()
    make_color(*ACCENT).setStroke()
    pulse.stroke()
    NSGraphicsContext.restoreGraphicsState()


def draw_app_icon() -> None:
    # called by → render_icon_png, once per size (always on the 1024 canvas)
    draw_icon_background()
    draw_sidebar_hint()
    draw_pulse_line()


def render_icon_png(pixel_size: int, output_file: Path) -> None:
    """
    LEARN: draw the icon at one pixel size and save it as a PNG

    called by → main, once per size
    NSBitmapImageRep = an empty picture in memory (RGBA, 8 bits per channel)
    the drawing is scaled from 1024 down to pixel_size → sharp at every size
    """
    image = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, pixel_size, pixel_size, 8, 4, True, False, "NSDeviceRGBColorSpace", 0, 0
    )
    context = NSGraphicsContext.graphicsContextWithBitmapImageRep_(image)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(context)
    context.setCompositingOperation_(NSCompositingOperationSourceOver)
    scale = NSAffineTransform.transform()
    scale.scaleBy_(pixel_size / DESIGN_SIZE)
    scale.concat()
    draw_app_icon()
    context.flushGraphics()
    NSGraphicsContext.restoreGraphicsState()
    png = image.representationUsingType_properties_(NSPNGFileType, {})
    png.writeToFile_atomically_(str(output_file), True)


def main() -> None:
    """
    LEARN: draw every size, then pack them into AppIcon.icns

    called by → make app_icon
    """
    # start from an empty .iconset folder each time
    shutil.rmtree(ICONSET_DIR, ignore_errors=True)
    ICONSET_DIR.mkdir(parents=True)
    for file_name, pixel_size in ICONSET_SIZES:
        render_icon_png(pixel_size=pixel_size, output_file=ICONSET_DIR / file_name)

    render_icon_png(pixel_size=DESIGN_SIZE, output_file=PREVIEW_FILE)
    # iconutil -c icns folder.iconset -o file.icns → the Mac icon file
    subprocess.run(
        [ICONUTIL_PATH, "-c", "icns", str(ICONSET_DIR), "-o", str(ICNS_FILE)],
        check=True,
    )
    shutil.rmtree(ICONSET_DIR)
    print(f"Wrote {ICNS_FILE} and {PREVIEW_FILE}")


# LEARN: this block runs only when the file is started directly
#   (python mac_app/make_icon.py), not when it's imported
if __name__ == "__main__":
    main()
