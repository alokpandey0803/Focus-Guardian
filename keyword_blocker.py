"""
Keyword & Blocked-Site Monitor — always watching, closes tabs on violations.

Two independent checks running in the same background thread:

1. KEYWORD mode (always active, in the browser):
   Watches the foreground window title (and page content via the browser
   extension) for blocked keywords — every keyword you add yourself, plus
   the built-in adult-content list IF the user has turned that on (it's
   off by default). Any match while a browser is in the foreground closes
   the active tab immediately, regardless of whether a timer or lock-in
   session is running.
   Outside the browser (title of a non-browser window, or clipboard
   contents) it fires a desktop notification with a motivational quote
   instead, since there's no tab to close.

2. SITE-BLOCK mode (active only during timer / lock-in):
   Watches foreground window title for any blocked site's domain name.
   Immediately closes the active browser tab (Ctrl+W) and notifies.
   Works regardless of incognito / regular mode / DNS-over-HTTPS — it does
   not touch the hosts file and does not break other open web apps.
"""
import platform
import re
import threading
import time

import psutil

from blocker import send_notification, random_quote as _random_quote


# ── Always-blocked explicit/adult-content terms ─────────────────────────────
# These are checked on EVERY tick, regardless of whether a timer/lock-in
# session is active. If any of these show up in the foreground window title
# (which for a browser usually reflects the page title / URL fragments),
# the active tab is closed immediately and a notification with a
# motivational quote is fired.
#
# NOTE / LIMITATION: this app has no access to the browser's real address
# bar or rendered page content (that would require a browser extension or
# admin-level hooks). It relies on the window/tab title as a heuristic, the
# same approach already used for blocked-site detection below. It will catch
# most adult sites (their titles/URLs almost always contain these terms) but
# is not a guaranteed, unbeatable content filter.
ADULT_CONTENT_KEYWORDS = {
    "porn", "pornhub", "xvideos", "xnxx", "xxx", "nsfw",
    "hentai", "onlyfans", "redtube", "youporn", "brazzers",
    "xhamster", "spankbang", "chaturbate", "livejasmin",
}


# ── Known browser process names ───────────────────────────────────────────────

BROWSER_PROCS = {
    "chrome", "chromium", "firefox", "msedge", "opera",
    "brave", "vivaldi", "iexplore", "safari", "waterfox",
    "librewolf", "arc",
}


# ── Platform helpers ──────────────────────────────────────────────────────────

def _get_foreground_title() -> str:
    """Return the title of the currently focused window (best-effort)."""
    try:
        sys = platform.system()
        if sys == "Windows":
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return ""
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        elif sys == "Darwin":
            import subprocess
            r = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get name of first process whose frontmost is true'],
                capture_output=True, text=True, timeout=2,
            )
            return r.stdout.strip()
        else:  # Linux
            import subprocess
            r = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True, text=True, timeout=2,
            )
            return r.stdout.strip()
    except Exception:
        return ""


def _get_foreground_pid() -> int | None:
    """Return the PID of the process owning the foreground window."""
    try:
        sys = platform.system()
        if sys == "Windows":
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            pid = ctypes.c_ulong(0)
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return pid.value if pid.value else None
        else:
            return None
    except Exception:
        return None


def _is_browser_foreground() -> bool:
    """Return True if a web browser currently has focus."""
    pid = _get_foreground_pid()
    if pid is None:
        # On Mac/Linux we can't cheaply get the PID — assume True so we
        # still attempt to close the tab if the title matches.
        return True
    try:
        proc = psutil.Process(pid)
        name = proc.name().lower()
        return any(b in name for b in BROWSER_PROCS)
    except Exception:
        return False


def _close_browser_tab() -> None:
    """
    Close the currently active browser tab via keyboard shortcut (Ctrl+W).
    Waits briefly to give the browser time to process the keypress.
    """
    sys = platform.system()
    try:
        if sys == "Windows":
            import ctypes
            VK_CONTROL = 0x11
            VK_W       = 0x57
            KEYDOWN, KEYUP = 0x0000, 0x0002
            ke = ctypes.windll.user32.keybd_event
            ke(VK_CONTROL, 0, KEYDOWN, 0)
            ke(VK_W,       0, KEYDOWN, 0)
            time.sleep(0.07)
            ke(VK_W,       0, KEYUP,   0)
            ke(VK_CONTROL, 0, KEYUP,   0)
        elif sys == "Darwin":
            import subprocess
            subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to keystroke "w" using command down'],
                timeout=2,
            )
        else:  # Linux
            import subprocess
            subprocess.run(["xdotool", "key", "ctrl+w"], timeout=2)
    except Exception:
        pass


def _get_clipboard() -> str:
    """Return clipboard text (best-effort, platform-specific)."""
    try:
        sys = platform.system()
        if sys == "Windows":
            import ctypes
            CF_UNICODETEXT = 13
            if not ctypes.windll.user32.OpenClipboard(0):
                return ""
            try:
                handle = ctypes.windll.user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return ""
                locked = ctypes.windll.kernel32.GlobalLock(handle)
                try:
                    return ctypes.wstring_at(locked)
                finally:
                    ctypes.windll.kernel32.GlobalUnlock(handle)
            finally:
                ctypes.windll.user32.CloseClipboard()
        elif sys == "Darwin":
            import subprocess
            r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=2)
            return r.stdout
        else:
            import subprocess
            for cmd in (
                ["xclip", "-selection", "clipboard", "-o"],
                ["xsel",  "--clipboard", "--output"],
            ):
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                if r.returncode == 0:
                    return r.stdout
            return ""
    except Exception:
        return ""


def _extract_site_root(domain: str) -> str:
    """
    'www.youtube.com' → 'youtube'
    'youtube.com'     → 'youtube'
    'youtube'         → 'youtube'
    """
    domain = domain.lower().strip().removeprefix("http://").removeprefix("https://").split("/")[0]
    parts = domain.split(".")
    # Strip www / common TLD suffixes to get the memorable root
    if parts[0] == "www" and len(parts) > 1:
        parts = parts[1:]
    if len(parts) >= 2:
        return parts[-2]   # 'youtube' from ['youtube', 'com']
    return parts[0] if parts else domain


def _contains_keyword(text: str, keyword: str) -> bool:
    """
    Whole-word match, not raw substring — so a keyword like 'car' matches
    "Used Car Deals" but NOT "scary", "card", "career", "NASCAR", etc.
    Multi-word keywords (e.g. "poker night") are matched as a phrase with
    word boundaries at each end.
    """
    if not keyword:
        return False
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return re.search(pattern, text) is not None


# ── Main class ────────────────────────────────────────────────────────────────

class KeywordBlocker:
    """
    Background thread that:
      • Always:  watches clipboard + window titles for blocked keywords.
                 During active blocking (timer/lock-in on) AND browser in
                 foreground: closes the tab immediately.
                 Otherwise: sends a motivational notification.
      • Active:  watches window titles for blocked site domain roots → closes
                 tab + sends notification.
    """

    def __init__(self, notify_callback=None, site_blocked_callback=None):
        """
        notify_callback(keyword, source, quote) — keyword detected (always active).
        site_blocked_callback(domain)            — site domain closed (blocking active).
        Both are called on the background thread; use .after(0, ...) for tkinter.
        """
        self._keywords:     set[str] = set()
        self._site_roots:   set[str] = set()   # derived roots of blocked domains
        # Always-on, independent of timer/lock-in state (custom extras, if any)
        self._always_block_keywords: set[str] = set()
        # OFF by default — the built-in adult-content list only applies once
        # the user explicitly turns it on. Some people don't want or need
        # this kind of monitoring at all, so it shouldn't run unasked.
        self._adult_content_enabled: bool = False
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._notify_callback = notify_callback
        self._site_blocked_callback = site_blocked_callback

        # Throttle — same keyword/domain at most once per N seconds
        self._last_kw_notif:   dict[str, float] = {}
        self._last_site_close: dict[str, float] = {}
        self._last_clipboard = ""

    # ── Public API ────────────────────────────────────────────────────────────

    def set_keywords(self, keywords: list[str]) -> None:
        with self._lock:
            self._keywords = {k.lower().strip() for k in keywords if k.strip()}

    def add_always_block_keywords(self, keywords: list[str]) -> None:
        """Extend the always-on (regardless of timer state) blocked-term list."""
        with self._lock:
            self._always_block_keywords |= {k.lower().strip() for k in keywords if k.strip()}

    def set_adult_content_blocking(self, enabled: bool) -> None:
        """Turn the built-in adult-content keyword list on/off. OFF by
        default — it only takes effect once the user explicitly ticks the
        option in Settings, so it never surprises or annoys someone who
        didn't ask for it. Doesn't affect the user's own custom keywords,
        which stay always-active regardless of this switch."""
        with self._lock:
            self._adult_content_enabled = bool(enabled)

    def set_active_blocked_sites(self, sites: list[str]) -> None:
        """
        Pass the current blocked-site list when blocking is active.
        Pass an empty list to deactivate site monitoring.
        Derives memorable root words (e.g. 'youtube' from 'youtube.com')
        so they can be matched against window titles.
        """
        roots = {_extract_site_root(s) for s in sites if s.strip()}
        with self._lock:
            self._site_roots = roots

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    # ── Internal loop ─────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while self._running:
            try:
                self._check()
            except Exception:
                pass
            time.sleep(0.5)   # check twice per second for snappy response

    def _check(self) -> None:
        with self._lock:
            keywords   = set(self._keywords)
            site_roots = set(self._site_roots)
            adult_kws  = set(ADULT_CONTENT_KEYWORDS) if self._adult_content_enabled else set()
            hard_kws   = set(self._always_block_keywords) | adult_kws | keywords  # user keywords now close too, always

        title = _get_foreground_title()
        title_lower = title.lower()

        # ── 0. Always-on close guard (built-in adult-content list + every ─────
        #      user-added keyword). Runs on every tick regardless of whether a
        #      focus session is active — matches are closed immediately.
        if hard_kws and _is_browser_foreground():
            for kw in hard_kws:
                if _contains_keyword(title_lower, kw):
                    now = time.time()
                    if now - self._last_site_close.get(f"hard:{kw}", 0) > 5:
                        self._last_site_close[f"hard:{kw}"] = now
                        _close_browser_tab()
                        time.sleep(0.1)
                        quote = _random_quote()
                        send_notification(
                            "🚫 Blocked Content Closed",
                            f'"{kw}" was detected and the tab was closed.\n{quote}',
                        )
                        if self._site_blocked_callback:
                            try:
                                self._site_blocked_callback(kw)
                            except Exception:
                                pass
                    return  # one action per tick

        # ── 1. Blocked-site tab closing (only when blocking is active) ────────
        if site_roots and _is_browser_foreground():
            for root in site_roots:
                if _contains_keyword(title_lower, root):
                    now = time.time()
                    if now - self._last_site_close.get(root, 0) > 5:
                        self._last_site_close[root] = now
                        _close_browser_tab()
                        time.sleep(0.1)  # let the close register
                        quote = _random_quote()
                        send_notification(
                            "🔒 Study Blocker — Blocked!",
                            f'"{root}" is blocked during your session. Tab closed.\n{quote}',
                        )
                        if self._site_blocked_callback:
                            try:
                                self._site_blocked_callback(root)
                            except Exception:
                                pass
                    return  # one action per tick

        # ── 2. Keyword detection — non-browser windows + clipboard ────────────
        # (Browser-tab matches are already handled and closed in step 0 above.)
        if keywords and not _is_browser_foreground():
            for kw in keywords:
                if _contains_keyword(title_lower, kw):
                    self._fire_keyword(kw, "page title")
                    return

        if keywords:
            # Check clipboard (only on change)
            clip = _get_clipboard().lower()
            if clip and clip != self._last_clipboard:
                self._last_clipboard = clip
                for kw in keywords:
                    if _contains_keyword(clip, kw):
                        self._fire_keyword(kw, "clipboard")
                        return

    def _fire_keyword(self, keyword: str, source: str) -> None:
        """Send a motivational notification (timer off / non-browser context)."""
        now = time.time()
        if now - self._last_kw_notif.get(keyword, 0) < 20:
            return
        self._last_kw_notif[keyword] = now
        quote = _random_quote()
        send_notification(
            "🔑 Stay Locked In!",
            f'Keyword "{keyword}" detected in {source}.\n{quote}',
        )
        if self._notify_callback:
            try:
                self._notify_callback(keyword, source, quote)
            except Exception:
                pass
