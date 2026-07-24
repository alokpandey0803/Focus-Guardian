"""
Console-free launcher for running FocusGuardian straight from source.

Double-click THIS file instead of main.py. Windows automatically runs
.pyw files with pythonw.exe (installed alongside regular Python) instead
of python.exe — same interpreter, same code, just no console window.

On top of that, this launcher checks for missing dependencies (customtkinter,
psutil, plyer, pillow, pystray) BEFORE importing the main app, and installs
whatever's missing automatically — with a small progress window, since a
.pyw process has no console to show pip's normal output in. This only
matters on first run on a fresh machine; if everything's already installed
it adds no delay and no window at all.

This is only needed while working from source. Once you build the .exe
with build_exe.bat, all dependencies are already baked in — you won't
need this file (or this check) at that point.
"""
import importlib
import os
import runpy
import subprocess
import sys
import threading

_here = os.path.dirname(os.path.abspath(__file__))

# import-name -> pip install spec
REQUIRED = {
    "customtkinter": "customtkinter>=5.2.0",
    "psutil":        "psutil>=5.9.0",
    "plyer":         "plyer>=2.1.0",
    "PIL":           "pillow>=10.0.0",
    "pystray":       "pystray>=0.19.5",
}


def _missing_packages() -> list[str]:
    missing = []
    for import_name, pip_spec in REQUIRED.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append(pip_spec)
    return missing


def _classify_install_error(exc: Exception, stderr: str) -> tuple[str, str]:
    """
    Turn a raw pip/subprocess failure into (short_reason, fix_instructions)
    the user can actually act on, instead of a bare Python traceback.
    """
    text = f"{stderr or ''} {exc}".lower()

    if isinstance(exc, FileNotFoundError) or "not recognized" in text or "no such file or directory" in text:
        return (
            "Python/pip isn't reachable on this system's PATH.",
            "How to fix it:\n"
            "1. Reinstall Python from https://www.python.org/downloads/\n"
            "2. On the FIRST install screen, tick \"Add python.exe to PATH\"\n"
            "   before clicking Install.\n"
            "3. If Python is already installed, add it to PATH manually:\n"
            "   • Press the Windows key, type \"Environment Variables\",\n"
            "     open \"Edit the system environment variables\".\n"
            "   • Click \"Environment Variables…\" near the bottom.\n"
            "   • Under \"User variables\", select \"Path\" → \"Edit\" → \"New\".\n"
            "   • Add the folder that contains python.exe (something like\n"
            "     C:\\Users\\<You>\\AppData\\Local\\Programs\\Python\\Python312\\)\n"
            "     AND its \\Scripts subfolder (that's where pip.exe lives).\n"
            "   • Click OK on every window, then close and reopen FocusGuardian."
        )

    if any(s in text for s in (
        "failed to establish a new connection", "getaddrinfo failed",
        "name or service not known", "connection timed out",
        "network is unreachable", "temporary failure in name resolution",
        "could not find a version", "no matching distribution",
        "read timed out",
    )):
        return (
            "No internet connection reached PyPI (Python's package server).",
            "How to fix it:\n"
            "1. Check that this computer is actually online.\n"
            "2. On a work/school network or VPN, it may be blocking pip —\n"
            "   try a different network, or ask IT to allow access to\n"
            "   pypi.org and files.pythonhosted.org.\n"
            "3. Behind a proxy? Set it before relaunching (Command Prompt):\n"
            "   set HTTPS_PROXY=http://your-proxy:port\n"
            "4. Once you're online, just reopen FocusGuardian — it retries\n"
            "   the install automatically."
        )

    if "permission" in text or "access is denied" in text or "winerror 5" in text:
        return (
            "Windows blocked the install (a permissions issue).",
            "How to fix it:\n"
            "1. Close this app.\n"
            "2. Right-click FocusGuardian.pyw (or your Command Prompt) and\n"
            "   choose \"Run as administrator\", then try again.\n"
            "3. Or, if you can't run as admin, open Command Prompt in this\n"
            "   folder and run:\n"
            f'   "{sys.executable}" -m pip install -r requirements.txt --user'
        )

    return (
        "An unexpected error happened during setup.",
        "Run this manually in a Command Prompt, in this folder, to see the\n"
        "full error message:\n"
        f'"{sys.executable}" -m pip install -r requirements.txt'
    )


def _install_with_progress(missing: list[str]) -> tuple[bool, str, str, str]:
    """Show a small setup window while installing missing packages.
    Returns (success, raw_error, reason, fix_instructions) — reason/fix are
    empty strings on success."""
    import tkinter as tk

    root = tk.Tk()
    root.title("FocusGuardian — First-time setup")
    root.geometry("440x160")
    root.resizable(False, False)
    root.configure(bg="#0F172A")
    # Center on screen
    root.update_idletasks()
    x = (root.winfo_screenwidth() - 440) // 2
    y = (root.winfo_screenheight() - 160) // 2
    root.geometry(f"+{x}+{y}")

    tk.Label(root, text="🔧 Setting up FocusGuardian", font=("Segoe UI", 14, "bold"),
             bg="#0F172A", fg="#F1F5F9").pack(pady=(22, 6))
    status = tk.Label(root, text="Checking required packages…",
                       font=("Segoe UI", 10), bg="#0F172A", fg="#94A3B8", wraplength=400)
    status.pack(pady=(0, 14))

    bar_bg = tk.Frame(root, bg="#1E293B", height=8, width=380)
    bar_bg.pack()
    bar_bg.pack_propagate(False)
    bar_fill = tk.Frame(bar_bg, bg="#3B82F6", height=8, width=0)
    bar_fill.place(x=0, y=0)

    result = {"ok": True, "error": "", "reason": "", "fix": ""}

    def worker():
        total = len(missing)
        for i, pkg in enumerate(missing, start=1):
            root.after(0, lambda p=pkg: status.config(text=f"Installing {p} ({i}/{total})…"))
            try:
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--quiet",
                     "--disable-pip-version-check", pkg],
                    check=True, creationflags=creationflags,
                    capture_output=True, text=True,
                )
            except Exception as e:
                stderr = getattr(e, "stderr", "") or ""
                reason, fix = _classify_install_error(e, stderr)
                result["ok"] = False
                result["error"] = str(e)
                result["reason"] = reason
                result["fix"] = fix
                break
            pct = i / total
            root.after(0, lambda p=pct: bar_fill.place(x=0, y=0, width=int(380 * p)))
        root.after(0, lambda: status.config(
            text="Done! Starting FocusGuardian…" if result["ok"] else "Setup failed."))
        root.after(500, root.destroy)

    threading.Thread(target=worker, daemon=True).start()
    root.mainloop()
    return result["ok"], result["error"], result["reason"], result["fix"]


def main():
    missing = _missing_packages()
    if missing:
        ok, error, reason, fix = _install_with_progress(missing)
        if not ok or _missing_packages():
            import tkinter as tk
            from tkinter import messagebox
            r = tk.Tk()
            r.withdraw()
            if not reason:
                # Every install step reported success but a package still
                # isn't importable afterward — rare, so no specific
                # cause was classified for it.
                reason = "Packages installed, but one is still not importable."
                fix = (
                    "Try running this manually in a Command Prompt, in this\n"
                    "folder, to see what's going on:\n"
                    f'"{sys.executable}" -m pip install -r requirements.txt'
                )
            messagebox.showerror(
                "Setup failed",
                "FocusGuardian couldn't automatically install some required "
                f"packages.\n\n{reason}\n\n{fix}",
            )
            r.destroy()
            return

    runpy.run_path(os.path.join(_here, "main.py"), run_name="__main__")


if __name__ == "__main__":
    main()
