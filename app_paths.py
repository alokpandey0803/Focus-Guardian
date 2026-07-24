"""
Stable, writable, per-user location for FocusGuardian's data files.

CRITICAL: this must never be derived from __file__ or the running script's
folder. When PyInstaller packages the app as a --onefile exe, the code
doesn't run from a fixed location — every launch unpacks into a brand new
temporary folder (sys._MEIxxxxxx) which Windows deletes again the moment
the app closes. Anything saved next to __file__ (config.json, stats.json)
was silently living inside that folder and vanishing on every restart.
Using the OS's real per-user app-data folder instead means the files
survive across restarts, exe rebuilds, and even moving the exe around.
"""
import os


def atomic_write_json(path: str, data) -> None:
    """
    Write JSON to `path` without ever leaving a half-written/corrupted
    file behind, even if the process is killed mid-write (e.g. Windows
    force-closing the app during a shutdown/restart that didn't finish
    in time). Writes to a temp file in the same folder first, then
    os.replace()'s it into place — that swap is atomic on both Windows
    and POSIX, so `path` always contains either the old complete
    contents or the new complete contents, never a truncated mix of
    both. Without this, a kill mid-write could corrupt the JSON file,
    and the loader's (correct, crash-avoiding) fallback of treating an
    unreadable file as "no data" would then look like every stored
    stat/setting had been silently reset to nothing.
    """
    import json
    tmp_path = f"{path}.tmp-{os.getpid()}"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


_APP_NAME = "FocusGuardian"


def data_dir() -> str:
    """Creates (if needed) and returns the per-user data folder."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(base, _APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def migrate_legacy_file(filename: str, legacy_dir: str) -> None:
    """One-time move of a data file that used to live next to the source
    script (only relevant for people who ran FocusGuardian.pyw before this
    fix) into the new stable location, so existing stats/config aren't
    lost in the switch. No-ops if there's nothing to migrate or the new
    file already exists."""
    new_path = os.path.join(data_dir(), filename)
    if os.path.exists(new_path):
        return
    legacy_path = os.path.join(legacy_dir, filename)
    if os.path.exists(legacy_path) and os.path.abspath(legacy_path) != os.path.abspath(new_path):
        try:
            import shutil
            shutil.copy2(legacy_path, new_path)
        except OSError:
            pass
