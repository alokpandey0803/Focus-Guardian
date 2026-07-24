"""
Single-instance guard.

Without this, if the tray icon ever fails to reappear (see tray_icon.py)
or you simply forget it's already running in the background, double-
clicking the app again launches a SECOND, fully independent process —
its own timer, its own AppBlocker/KeywordBlocker, its own idea of whether
Lock-In is on. The first (invisible) copy keeps enforcing whatever
blocking state it had, which is exactly why blocking can look "stuck on"
even after you turn Lock-In/timer off in the window you can see: you're
looking at the new process, not the one still doing the blocking.

This uses a localhost-only TCP socket as both a lock and a tiny IPC
channel:
  - The first instance binds the port and keeps listening in the
    background. Binding it is the "lock" — only one process can hold it.
  - Any later launch attempt fails to bind (port already taken), so it
    knows an instance is already running. It connects to that port,
    sends a "SHOW" message, and should then exit immediately instead of
    starting a second app.
  - The first instance, on receiving "SHOW", calls the callback it was
    given (marshalled onto the Tk thread by the caller) to restore its
    window — so "opening the app again" always reaches the one true
    running instance instead of spawning a duplicate.
"""
import os
import socket
import threading

# Arbitrary fixed high port, localhost-only. Only used as a lock +
# same-machine signal — never exposed to the network.
DEFAULT_PORT = 51823


class SingleInstance:
    def __init__(self, on_show_requested, port: int = DEFAULT_PORT):
        """
        on_show_requested() — called (on a background thread; marshal to
        the Tk thread yourself) whenever another launch attempt asks the
        running instance to come to the foreground.
        """
        self._on_show_requested = on_show_requested
        self._port = port
        self._sock: socket.socket | None = None

    def try_acquire(self) -> bool:
        """
        Returns True if this process is the (only) running instance and
        should proceed to start the app normally.

        Returns False if another instance is already running — in that
        case it has already been signalled to show its window, and this
        process should exit right away without building any app state.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if os.name == "nt":
                # On Windows, SO_REUSEADDR does NOT behave like it does on
                # Linux/Mac — it lets a second process bind this exact
                # port even while the first is actively listening, which
                # silently defeated the whole point of using bind() as a
                # lock (both copies would think they were "first" and
                # both would fully start — this was the actual cause of
                # seeing two tray icons at once). SO_EXCLUSIVEADDRUSE is
                # the Windows-specific option that gives real exclusive
                # ownership of the port.
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", self._port))
        except OSError:
            s.close()
            self._signal_existing_instance()
            return False

        s.listen(5)
        self._sock = s
        threading.Thread(target=self._serve, daemon=True).start()
        return True

    def _signal_existing_instance(self) -> None:
        try:
            with socket.create_connection(("127.0.0.1", self._port), timeout=2) as c:
                c.sendall(b"SHOW\n")
        except OSError:
            # Best-effort — if even this fails, just let this launch
            # proceed normally rather than silently doing nothing.
            pass

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            try:
                data = conn.recv(64)
            except OSError:
                data = b""
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
            if data.strip() == b"SHOW":
                try:
                    self._on_show_requested()
                except Exception:
                    pass
