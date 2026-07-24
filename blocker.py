"""
Core blocking logic:
  - Desktop app blocking via psutil process monitoring
  - Desktop notifications via plyer

NOTE: Hosts-file website blocking has been removed. It caused browser DoH to
bypass blocks in regular (non-incognito) mode and disrupted all other open web
apps by poisoning existing connections. Website blocking is now handled entirely
by the KeywordBlocker title monitor, which closes the active browser tab the
moment a blocked domain appears in the window title — works in every mode
(regular, incognito, guest) without touching system files.
"""
import platform
import random
import threading
import time
import psutil

try:
    from plyer import notification as plyer_notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False


# ── Motivational quotes (shared with keyword_blocker) ──────────────────────────

QUOTES = [
    "Your future self is watching — make them proud.",
    "Every distraction you resist is a rep for your willpower.",
    "Champions do what they don't feel like doing.",
    "Success is the sum of small efforts repeated day in and day out.",
    "You didn't come this far to only come this far.",
    "Discipline is choosing between what you want now and what you want most.",
    "The pain of discipline is far less than the pain of regret.",
    "Do it now — your future self will thank you.",
    "Focus on the step in front of you, not the whole staircase.",
    "Great things are done by a series of small things brought together.",
    "Your only limit is your mind. Reset it. Stay focused.",
    "Don't watch the clock — do what it does. Keep going.",
    "A year from now you'll wish you had started today.",
    "One hour of focused work beats five hours of distracted work.",
    "Temporary distractions lead to permanent regrets.",
    "You are closer than you think. Keep pushing.",
    "Motivation gets you started — discipline keeps you going.",
    "Every expert was once a beginner who refused to give up.",
    "The secret of getting ahead is getting started — right now.",
    "Be stronger than your excuses.",
    "Hard work beats talent when talent doesn't work hard.",
    "You've got this. Close the tab and get back to work.",
    "Distractions are expensive — pay attention to what matters.",
    "Success requires sacrifice. This is your sacrifice moment.",
    "Stay locked in. The world can wait.",
]


def random_quote() -> str:
    return random.choice(QUOTES)


# ── Notifications ─────────────────────────────────────────────────────────────

def send_notification(title: str, message: str) -> None:
    """Send a desktop notification (falls back to print if unavailable)."""
    if PLYER_AVAILABLE:
        try:
            plyer_notification.notify(
                title=title,
                message=message,
                app_name="Study Blocker",
                timeout=6,
            )
            return
        except Exception:
            pass
    print(f"[NOTIFICATION] {title}: {message}")


# ── Website blocking stubs (hosts-file approach removed) ──────────────────────
# These are kept as no-ops so existing callers don't break. Website blocking is
# now handled by KeywordBlocker (title monitor + Ctrl+W tab closing).

def has_hosts_permission() -> bool:
    """No-op stub — hosts-file blocking removed."""
    return True


def apply_website_blocks(sites: list[str]) -> bool:
    """No-op stub — website blocking is handled by KeywordBlocker."""
    return True


def remove_all_website_blocks() -> None:
    """No-op stub — website blocking is handled by KeywordBlocker."""
    pass


# ── Desktop app blocker ───────────────────────────────────────────────────────

class AppBlocker:
    """
    Background thread that continuously scans running processes.
    Any process whose name or exe path contains a blocked pattern is killed
    immediately and the user is notified.
    """

    def __init__(self, notify_callback=None):
        """
        notify_callback(process_name: str) — called when a process is killed.
        Called on the background thread; use .after(0, ...) for tkinter.
        """
        self._blocked: set[str] = set()
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._killed_recently: dict[str, float] = {}
        self._notify_callback = notify_callback

    # ── Public API ────────────────────────────────────────────────────────────

    def set_blocked_apps(self, apps: list[str]) -> None:
        with self._lock:
            self._blocked = {a.lower().strip() for a in apps}

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    # ── internal ──────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while self._running:
            self._scan()
            time.sleep(1)   # scan every second for fast response

    def _scan(self) -> None:
        with self._lock:
            blocked = set(self._blocked)
        if not blocked:
            return

        now = time.time()
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                name = (proc.info["name"] or "").lower()
                exe  = (proc.info["exe"]  or "").lower()
                for pattern in blocked:
                    if pattern in name or pattern in exe:
                        last = self._killed_recently.get(pattern, 0)
                        if now - last > 10:
                            self._killed_recently[pattern] = now
                            send_notification(
                                "🔒 App Closed",
                                f"'{proc.info['name']}' is blocked and was closed.\n{random_quote()}",
                            )
                            if self._notify_callback:
                                self._notify_callback(proc.info["name"])
                        try:
                            proc.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
