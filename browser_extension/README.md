# FocusGuardian Content Blocker (browser extension)

This is the piece that actually reads page content — the desktop app alone
can't see inside your browser (no admin hook, no DOM access). This extension
runs as part of the page itself, so it can read the real title *and*
visible text and close the tab the moment a blocked term shows up.

It's an unpacked developer extension (not published on the Chrome Web
Store), so install it manually — takes under a minute.

## Install (Chrome, Edge, Brave — any Chromium browser)

1. Open `chrome://extensions` (or `edge://extensions`, `brave://extensions`).
2. Turn on **Developer mode** (toggle, top-right).
3. Click **Load unpacked**.
4. Select this `browser_extension` folder.
5. Pin it to the toolbar if you want (puzzle-piece icon → pin).

That's it — it's now watching every tab.

## What it does

- On every page, it reads the page **title and visible text** (not just the
  window title the desktop app can see) and checks it against a blocked-term
  list.
- If it finds a match, it shows a full-page "blocked" overlay with a
  motivational quote, fires a system notification, and closes the tab.
- It re-scans as the page changes (works on single-page apps like YouTube,
  Reddit, X/Twitter that load content without a full page reload).

## Managing keywords

Click the toolbar icon → **Manage keywords**, or right-click the icon →
**Options**. You can:
- See the built-in list (porn, adult-site names, etc.) — always on.
- Add your own custom keywords (gambling, specific sites, whatever you
  want blocked).
- Toggle scanning on/off entirely.

## Limitations, honestly

- It can't see inside PDFs viewed in-browser, images, or video content
  itself — only text the browser exposes as page text/DOM.
  Video/site *titles* are still caught.
- It runs per-browser-profile. If someone opens a different browser or a
  separate Chrome profile without this extension installed, it won't be
  scanning there.
- It's a keyword filter, not a machine-learning content classifier — it
  won't catch content that doesn't happen to use any of the listed terms.
- This is a self-install dev extension; someone with access to
  `chrome://extensions` on the same machine could disable it. Pairing it
  with the desktop app's Lock-In mode (which requires a password to exit)
  is the closest this setup gets to tamper-resistance.
