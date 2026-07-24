# Building FocusGuardian.exe

## Why you need to run this yourself, on Windows

I built and tested the packaging recipe on my (Linux) side to make sure
there are no missing-import errors — there aren't. But PyInstaller
**doesn't cross-compile**: a Windows `.exe` can only be produced by running
PyInstaller *on* Windows. There's no way around that from here, so the
build script below does the whole thing for you in under two minutes.

## Steps

1. Make sure **Python 3.10+** is installed on the Windows machine
   ([python.org](https://www.python.org/downloads/) — tick "Add Python to
   PATH" during install).
2. Copy this whole `FocusGuardian` folder onto that machine (this is a
   one-time thing — after this you only ever touch the resulting .exe).
3. Double-click **`build_exe.bat`** (or run it from a Command Prompt inside
   the folder).
4. When it finishes, your app is at `dist\FocusGuardian.exe` — a single
   file. That's the one you actually use and share from now on.

## This is exactly what you asked for

- **One single file.** `--onefile` bundles the Python interpreter, every
  library, and your code into that one `.exe`. Nothing else is needed —
  not the source folder, not Python installed, nothing.
- **Double-click → app opens directly.** No extra step, no "open the
  Python file" — the icon *is* the app.
- **No console window, ever, on anyone's PC.** `--windowed` means no cmd
  prompt is created in the first place — for you or for whoever you send
  it to. There's nothing to "close by accident"; the app runs until you
  actually exit it (the "Run in Background / Exit App" dialog, or Exit
  from the tray icon).
- **Shareable.** Send `FocusGuardian.exe` to a friend directly (email,
  USB stick, cloud link, however) — no code, no folder, no setup on their
  end. They double-click it and it runs, same as it does for you.
- **Custom icon.** `--icon=icon.ico` gives it a proper lock icon instead of
  the generic Python icon, so it looks like a real app in File Explorer,
  the taskbar, and the tray.

## One honest heads-up: antivirus / SmartScreen

I can't make Windows Defender or SmartScreen never flag an unsigned,
freshly-built exe — nobody can, for any indie app not signed by a paid
certificate. What I've done to minimize it:

- `--noupx` avoids UPX compression, which is a common AV trigger.

What you (and your friend) will most likely see is Windows SmartScreen's
**"Windows protected your PC"** the very first time it's run on a given
machine — that's not a virus detection, just "this file has no reputation
yet." Click **More info → Run anyway**, and it won't ask again on that PC.
If your friend is nervous about this, it's a completely normal step for
any small, unsigned tool — VS Code extensions, indie games, and countless
open-source utilities trigger the same prompt on first run.

The only way to remove that prompt entirely, for everyone, permanently, is
a paid code-signing certificate (~$100–400/year) — genuinely outside what
any build script can do, so I'd rather tell you that plainly than pretend
otherwise.

## Launch automatically when Windows starts

Built into the app: **⚙️ Settings** tab → **"Launch when Windows starts."**
It points the startup registry entry at wherever `FocusGuardian.exe`
currently lives, so this keeps working correctly even as a single shared
exe file — just make sure it's toggled off/on again if you move the exe to
a new folder later.

## Notes

- If you ever change the code, just re-run `build_exe.bat` — it overwrites
  `dist\FocusGuardian.exe` with the new build.
- First launch of a `--onefile` exe is a touch slower than later launches
  (it's unpacking itself into a temp folder each run) — a second or two,
  not noticeable in normal use.
- The app-killing / tab-closing / startup-registry features only work on
  Windows, which is fine since that's what you're building for.
