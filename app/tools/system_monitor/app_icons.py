"""Real app icons for the top apps list."""

import base64
import logging
import threading

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

ICON_SIZE_POINTS = 32
RETINA_SCALE = 2


class AppIconCache:
    """
    Looks up each app's Finder icon once and keeps it as a small PNG data URL.

    LEARN: PyObjC exposes Apple's Objective C classes to Python. A method like
    iconForFile: becomes iconForFile_ (each colon turns into an underscore).
    """

    def __init__(self, size_points: int = ICON_SIZE_POINTS) -> None:
        self._size_points = size_points
        self._lock = threading.Lock()
        self._icons: dict[str, str | None] = {}

    def get_app_icon_data_url(self, bundle_path: str) -> str | None:
        with self._lock:
            if bundle_path in self._icons:
                return self._icons[bundle_path]

        png = self._render_app_icon_png(bundle_path)
        data_url = (
            f"data:image/png;base64,{base64.b64encode(png).decode()}" if png else None
        )
        with self._lock:
            self._icons[bundle_path] = data_url

        return data_url

    def _render_app_icon_png(self, bundle_path: str) -> bytes | None:
        try:
            image = NSWorkspace.sharedWorkspace().iconForFile_(bundle_path)
            size = self._size_points
            pixels = size * RETINA_SCALE
            # LEARN: an app icon holds many sizes, up to 1024 px. Drawing it
            # into a small blank bitmap keeps only what the row needs (a few KB
            # instead of nearly 1 MB per icon).
            bitmap = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
                None, pixels, pixels, 8, 4, True, False, NSDeviceRGBColorSpace, 0, 0
            )
            bitmap.setSize_((size, size))
            NSGraphicsContext.saveGraphicsState()
            try:
                NSGraphicsContext.setCurrentContext_(
                    NSGraphicsContext.graphicsContextWithBitmapImageRep_(bitmap)
                )
                image.drawInRect_fromRect_operation_fraction_(
                    ((0, 0), (size, size)), NSZeroRect, NSCompositingOperationCopy, 1.0
                )
            finally:
                NSGraphicsContext.restoreGraphicsState()

            png = bitmap.representationUsingType_properties_(NSPNGFileType, {})
            return bytes(png)
        except Exception as error:
            logger.warning(f"App icon lookup failed {bundle_path=} {error=}")
            return None
