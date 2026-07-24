# 🔒 FocusGuardian

A Windows focus/distraction-blocker app — websites, apps, and keywords, plus a
Pomodoro-style timer and a strict "Lock-In Mode" for when you really can't be
trusted with an unlock button.

## Why I built this

I was juggling multiple different blocker apps to get everything I wanted —
website blocking from one, app blocking from another, a strict lock mode from
a third — and some of them were paid. I didn't want to keep paying for (or
babysitting) five different tools to do one job, so I built one app that does
all of it myself, for free, exactly the way I wanted it to work.

## Features

- **Website blocking** — closes the tab the instant a blocked site is opened, no admin rights or hosts-file hacking needed
- **App blocking** — kills matching processes the moment they launch
- **Keyword blocker** — always on, watches window titles/clipboard (plus real page content via the included browser extension) for words you don't want to see; closes the tab or nudges you with a notification
- **Optional adult content filter** — off by default, opt-in, doesn't get in your way unless you turn it on
- **Study timer** — simple focus-session timer that activates blocking while it runs
- **Lock-In Mode** — a stricter mode with a password you have to fully retype to exit early; while it's active you can *add* more restrictions but can't remove any until it ends
- **Stats tracking** — daily/weekly focused-time history, safe against crashes and PC restarts
- **Runs from the system tray**, with an option to launch on Windows startup

## Honesty about how this was built

I'm not going to pretend this was 100% hand-written — most of it was built by
**vibe-coding with Claude (Anthropic's AI)**: I described what I wanted, it
wrote and debugged the code, and I tested, used, and refined it in the real
world. I also wrote and edited some of it myself along the way. I'm still
learning to code properly, and the plan is to get better at it and build more
of my future projects by hand. This is a solo, non-professional project — it
won't be bug-free, and no blocker (AI-built or otherwise) can replace your
own willpower. It can only make distraction a little more inconvenient.

## Getting started

### Run from source
```
pip install -r requirements.txt
python FocusGuardian.pyw
```
Missing packages are auto-installed on first run; if that fails it'll tell
you exactly what to fix (network/PATH/permissions).

### Build a standalone .exe
```
build_exe.bat
```
Produces `dist/FocusGuardian.exe` — a single file, no Python required on the
machine you send it to.

### Build a full installer (desktop icon, Start Menu, launch-on-finish)
Install [Inno Setup](https://jrsoftware.org/isdl.php) (free), then compile
`FocusGuardian.iss`. Or just push this repo to GitHub — `.github/workflows/build.yml`
builds both the exe and the installer automatically and hands you a download
from the Actions tab, no local setup needed.

## Tech stack

Python, [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) for
the UI, `psutil` for process monitoring, `pystray` for the tray icon,
PyInstaller for packaging, and a small Chrome extension for real page-content
scanning.

## License

MIT + Commons Clause — see [LICENSE](LICENSE). Use it, learn from it, modify
it, share it — just keep the credit intact, and don't sell it or a product
built on it.

## Contact

Built by **Alok Pandey**.
[GitHub](https://github.com/alokpandey0803) ·
[LinkedIn](https://www.linkedin.com/in/alok-pandey-609259378/) — feel free to
connect, I'd love to hear from you.
