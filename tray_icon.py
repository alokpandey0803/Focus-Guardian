"""
System tray icon for FocusGuardian.

Lets the app keep running (timers, blocking, keyword scanning all stay
active) with its window hidden and no taskbar entry — same pattern as the
tray-only apps in the Windows notification area (IDE background agents,
Java updater, antivirus, etc.).

pystray's Icon.run() blocks, so it's started on its own daemon thread.
Its callbacks fire on THAT thread, not the Tkinter thread — callers must
marshal back onto the Tk main loop themselves (e.g. via `self.after(0, …)`)
before touching any widgets.

IMPORTANT: a fresh pystray.Icon is created on every show() call instead of
reusing one instance across hide()/show() cycles. Re-calling run() on an
Icon that has already been stop()'d is unreliable — on Windows in
particular, the backend doesn't fully reset its internal window handle
state after stop(), so a second run() can silently produce no visible
icon at all while still leaving the thread "alive". That's what caused
the icon to work the first time you minimized to tray but vanish for
good on the next one.
"""
import threading

import pystray
from PIL import Image, ImageDraw


def _build_icon_image() -> Image.Image:
    """Small generated lock-badge icon — no external asset needed."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 4, size - 4, size - 4], radius=16, fill=(59, 130, 246, 255))
    # simple padlock glyph
    d.rounded_rectangle([20, 30, 44, 50], radius=4, fill=(15, 23, 42, 255))
    d.arc([22, 14, 42, 36], start=180, end=360, fill=(15, 23, 42, 255), width=5)
    return img


class TrayIcon:
    """Wraps a pystray.Icon with Open / Exit menu items."""

    def __init__(self, on_open, on_exit, tooltip: str = "FocusGuardian — running in background"):
        self._on_open = on_open
        self._on_exit = on_exit
        self._tooltip = tooltip
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _build_icon(self) -> pystray.Icon:
        return pystray.Icon(
            "FocusGuardian",
            _build_icon_image(),
            self._tooltip,
            menu=pystray.Menu(
                pystray.MenuItem("Open FocusGuardian", self._handle_open, default=True),
                pystray.MenuItem("Exit", self._handle_exit),
            ),
        )

    def _handle_open(self, icon, item):
        self._on_open()

    def _handle_exit(self, icon, item):
        self._on_exit()

    def show(self) -> None:
        """Start showing the tray icon (no-op if already showing)."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._icon = self._build_icon()
            icon = self._icon
            self._thread = threading.Thread(target=icon.run, daemon=True)
            self._thread.start()

    def hide(self) -> None:
        """Remove the tray icon and drop the underlying pystray.Icon so the
        next show() always starts from a clean instance."""
        with self._lock:
            icon = self._icon
            self._icon = None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
        # Give the icon's message-loop thread a brief moment to actually
        # exit so is_alive() in the next show() reflects reality instead
        # of racing a still-tearing-down thread.
        if self._thread is not None:
            self._thread.join(timeout=1.0)
