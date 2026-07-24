"""
Windows "launch at startup" manager.

Uses the per-user registry Run key
(HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run)
rather than the Startup folder or a scheduled task — no admin rights
needed, and it's the same mechanism most consumer apps use.

No-ops safely on non-Windows platforms (so this file is safe to import
during development on Mac/Linux too).
"""
import os
import platform
import sys

APP_NAME = "FocusGuardian"


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _launch_command() -> str:
    """
    Build the command Windows should run at login.

    - If we're running as a frozen PyInstaller .exe (sys.frozen is set),
      point straight at that exe — no Python/cmd window involved.
    - If running from source (`python main.py`), fall back to invoking
      pythonw.exe (the windowless Python launcher) with this script's
      path, so no console flashes up on login either way.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = os.path.abspath(sys.argv[0])
    python_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(python_dir, "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable  # fallback, best-effort
    return f'"{pythonw}" "{script}"'


def is_startup_enabled() -> bool:
    if not _is_windows():
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ,
        )
        try:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
        finally:
            winreg.CloseKey(key)
    except FileNotFoundError:
        return False
    except Exception:
        return False


def enable_startup() -> bool:
    """Add FocusGuardian to the per-user startup list. Returns success."""
    if not _is_windows():
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        try:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _launch_command())
        finally:
            winreg.CloseKey(key)
        return True
    except Exception:
        return False


def disable_startup() -> bool:
    """Remove FocusGuardian from the per-user startup list. Returns success."""
    if not _is_windows():
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        try:
            winreg.DeleteValue(key, APP_NAME)
        finally:
            winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return True  # already not there — that's fine
    except Exception:
        return False
