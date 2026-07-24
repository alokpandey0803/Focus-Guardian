"""
Study timer logic — counts down from a given number of minutes and
fires a callback when it reaches zero.
"""
import threading
import time


class StudyTimer:
    def __init__(self, on_tick=None, on_finish=None):
        """
        on_tick(remaining_seconds)  — called every second
        on_finish()                 — called when timer reaches zero
        """
        self._on_tick = on_tick
        self._on_finish = on_finish
        self._total_seconds = 0
        self._remaining = 0
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        # Bumped on every start()/pause()/stop(). A running loop thread
        # captures the generation it was born with and checks it on every
        # tick — if a newer generation exists, it knows it's stale and
        # exits immediately instead of touching shared state.
        #
        # Without this, calling start() while a timer is already running
        # (e.g. clicking a different preset button mid-session) could
        # leave the OLD loop thread asleep in time.sleep(1) at the exact
        # moment the new one starts. stop()'s _running=False gets
        # overwritten back to True by the new start() before the old
        # thread wakes up and rechecks it — so it sees "running" and
        # keeps decrementing _remaining too. Two threads both ticking the
        # same counter down = the timer visibly resets, then runs ~2x
        # fast. The generation check closes that race regardless of
        # timing, since a stale thread's generation never matches again.
        self._generation = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, minutes: int) -> None:
        with self._lock:
            self._generation += 1
            gen = self._generation
            self._total_seconds = minutes * 60
            self._remaining = self._total_seconds
            self._running = True
        self._thread = threading.Thread(target=self._loop, args=(gen,), daemon=True)
        self._thread.start()

    def pause(self) -> None:
        with self._lock:
            self._running = False
            self._generation += 1  # invalidate any in-flight loop thread

    def resume(self) -> None:
        with self._lock:
            if self._running or self._remaining <= 0:
                return
            self._generation += 1
            gen = self._generation
            self._running = True
        self._thread = threading.Thread(target=self._loop, args=(gen,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._remaining = 0
            self._generation += 1

    def add_minutes(self, minutes: int) -> None:
        with self._lock:
            self._remaining = max(0, self._remaining + minutes * 60)

    @property
    def remaining(self) -> int:
        return self._remaining

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Internal ──────────────────────────────────────────────────────────────

    def _loop(self, gen: int) -> None:
        while True:
            time.sleep(1)
            with self._lock:
                if gen != self._generation or not self._running:
                    return  # stale thread (superseded) or paused/stopped
                self._remaining = max(0, self._remaining - 1)
                remaining = self._remaining
                finished = remaining == 0
                if finished:
                    self._running = False
            # Fire callbacks outside the lock — they call back into the
            # GUI (via .after / tkinter vars) and shouldn't run while we're
            # holding a lock other timer methods might need.
            if self._on_tick:
                self._on_tick(remaining)
            if finished:
                if self._on_finish:
                    self._on_finish()
                return
