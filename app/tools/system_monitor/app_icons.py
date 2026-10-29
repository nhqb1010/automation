# LEARN: YOU ARE HERE
#   top apps reader ▶ THIS FILE turns an app's icon into a small picture
#   ▶ text inside the TopApps JSON ▶ <img> in each app row on the page
#   read next → app/tools/system_monitor/storage.py
"""Real app icons for the top apps list."""

# LEARN: base64 = a way to write raw bytes (like a PNG picture) as plain text
#   → the picture can travel inside JSON to the page
import base64
import logging
import threading

# LEARN: AppKit = Apple's macOS UI library (written in Objective-C)
#   PyObjC (installed with pywebview) lets Python use it directly
#   Objective-C method names have colons; in Python each ":" becomes "_"
#     iconForFile:  →  iconForFile_(path)
from AppKit import (
    NSBitmapImageRep,
    NSCompositingOperationCopy,
    NSDeviceRGBColorSpace,
    NSGraphicsContext,
    NSPNGFileType,
    NSWorkspace,
    NSZeroRect,
)

logger = logging.getLogger(__name__)

# LEARN: "points" = screen size units; a Retina screen has 2 pixels per point
#   → draw at 64 × 64 pixels so a 32-point icon stays sharp
ICON_SIZE_POINTS = 32
RETINA_SCALE = 2


class AppIconCache:
    """
    LEARN: each app's Finder icon, made once, kept as a small picture text

    made by → the top apps reader, once at startup
    called by → the top apps reader, for every app row, every refresh
    gives back → "data:image/png;base64,…" text, or None

    data URL = a whole picture written inside a text string
      the page can use it as an <img> source directly, no file needed

    cache = first request does the slow work, later ones reuse the result
      ✓ icon drawing happens once per app, not every 2 s
    """

    def __init__(self, size_points: int = ICON_SIZE_POINTS) -> None:
        self._size_points = size_points
        self._lock = threading.Lock()
        # app folder path → finished data URL (or None if it failed)
        self._icons: dict[str, str | None] = {}

    def get_app_icon_data_url(self, bundle_path: str) -> str | None:
        # already made? → return it straight away
        with self._lock:
            if bundle_path in self._icons:
                return self._icons[bundle_path]

        # LEARN: the slow drawing happens OUTSIDE the lock
        #   → other threads aren't blocked while one icon is being drawn
        png = self._render_app_icon_png(bundle_path)
        # b64encode → bytes as base64; .decode() → turn those bytes into text
        data_url = (
            f"data:image/png;base64,{base64.b64encode(png).decode()}" if png else None
        )
        with self._lock:
            self._icons[bundle_path] = data_url

        return data_url

    def _render_app_icon_png(self, bundle_path: str) -> bytes | None:
        try:
            # LEARN: NSWorkspace.sharedWorkspace() = macOS's "Finder helper"
            #   iconForFile_ → the same icon Finder shows for that app
            image = NSWorkspace.sharedWorkspace().iconForFile_(bundle_path)
            size = self._size_points
            pixels = size * RETINA_SCALE

            # LEARN: an app icon holds many sizes, up to 1024 px (~1 MB)
            #   → draw it into a small blank picture → keep ~10 KB only
            #
            # LEARN: Objective-C object creation = two steps
            #   .alloc() → reserve memory; .init…(…) → fill it in
            #   this init's long name = one Objective-C method with 10 labelled
            #   arguments: no data yet, 64 × 64, 8 bits per colour,
            #   4 channels (red, green, blue, alpha / transparency), …
            bitmap = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
                None, pixels, pixels, 8, 4, True, False, NSDeviceRGBColorSpace, 0, 0
            )
            bitmap.setSize_((size, size))

            # LEARN: "graphics context" = where drawing commands land
            #   save → switch drawing to OUR small picture → draw → restore
            #   restore in finally → drawing is switched back even on error
            NSGraphicsContext.saveGraphicsState()
            try:
                NSGraphicsContext.setCurrentContext_(
                    NSGraphicsContext.graphicsContextWithBitmapImageRep_(bitmap)
                )
                # draw the whole icon into the box (0, 0) → (size, size)
                # NSZeroRect = "use the whole source picture"
                image.drawInRect_fromRect_operation_fraction_(
                    ((0, 0), (size, size)), NSZeroRect, NSCompositingOperationCopy, 1.0
                )
            finally:
                NSGraphicsContext.restoreGraphicsState()

            # save the small picture as PNG bytes
            png = bitmap.representationUsingType_properties_(NSPNGFileType, {})
            return bytes(png)
        # any problem → log it, no icon (the page shows a generic one)
        except Exception as error:
            logger.warning(f"App icon lookup failed {bundle_path=} {error=}")
            return None
