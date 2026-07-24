// FocusGuardian content script
// Runs inside every page. Reads the page's real title + visible text
// (not just the window/tab title) and closes the tab if a blocked
// keyword is found anywhere in it.

(function () {
  let closed = false;
  let scanScheduled = false;

  function escapeRegex(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function buildRegexes(keywords) {
    return keywords
      .filter(Boolean)
      .map((k) => new RegExp("\\b" + escapeRegex(k.toLowerCase()) + "\\b", "i"));
  }

  function getVisibleText() {
    // Title covers the URL/tab-title case; body.innerText covers real
    // rendered page content (articles, comments, video titles, etc.)
    const title = document.title || "";
    let body = "";
    try {
      body = document.body ? document.body.innerText.slice(0, 300000) : "";
    } catch (e) {
      body = "";
    }
    return title + "\n" + body;
  }

  function findMatch(keywords) {
    if (!keywords.length) return null;
    const regexes = buildRegexes(keywords);
    const text = getVisibleText();
    for (const re of regexes) {
      const m = text.match(re);
      if (m) return m[0];
    }
    return null;
  }

  function showOverlayAndClose(keyword) {
    if (closed) return;
    closed = true;
    const quote = typeof randomQuote === "function" ? randomQuote() : "Stay focused.";

    try {
      const overlay = document.createElement("div");
      overlay.setAttribute("data-focusguardian", "1");
      overlay.style.cssText =
        "position:fixed;inset:0;z-index:2147483647;background:#0F172A;color:#F1F5F9;" +
        "display:flex;flex-direction:column;align-items:center;justify-content:center;" +
        "font-family:-apple-system,'Segoe UI',sans-serif;text-align:center;padding:40px;";
      overlay.innerHTML =
        '<div style="font-size:44px;margin-bottom:14px;">🔒</div>' +
        '<div style="font-size:20px;font-weight:700;margin-bottom:10px;">Blocked by FocusGuardian</div>' +
        '<div style="font-size:14px;color:#94A3B8;margin-bottom:18px;">Blocked content detected on this page</div>' +
        '<div style="font-size:16px;max-width:460px;line-height:1.5;">' + quote + "</div>" +
        '<div style="font-size:12px;color:#64748B;margin-top:22px;">Closing this tab…</div>';
      (document.documentElement || document.body).appendChild(overlay);
      document.documentElement.style.overflow = "hidden";
    } catch (e) {
      // If we can't render the overlay (very early document_start), skip it.
    }

    try {
      chrome.runtime.sendMessage({ type: "FG_CLOSE_TAB", keyword, quote });
    } catch (e) {
      // Extension context may be unavailable; nothing more we can do.
    }
  }

  function runScan() {
    if (closed) return;
    chrome.storage.sync.get(["customKeywords", "enabled", "blockAdultContent"], (data) => {
      if (chrome.runtime.lastError) return;
      const enabled = data.enabled !== false; // default: on
      if (!enabled) return;
      const custom = Array.isArray(data.customKeywords) ? data.customKeywords : [];
      const adultOptIn = data.blockAdultContent === true; // default: off
      const all = [...(adultOptIn ? DEFAULT_KEYWORDS : []), ...custom]
        .map((k) => String(k).toLowerCase().trim());
      const hit = findMatch(all);
      if (hit) showOverlayAndClose(hit);
    });
  }

  function scheduleScan() {
    if (scanScheduled || closed) return;
    scanScheduled = true;
    setTimeout(() => {
      scanScheduled = false;
      runScan();
    }, 250); // throttle: content mutates rapidly on many sites
  }

  // Initial scans: as early as possible, then again once the DOM is ready
  // (document_start fires before <body> exists on many sites).
  runScan();
  document.addEventListener("DOMContentLoaded", runScan);
  window.addEventListener("load", runScan);

  // Keep watching — SPAs (YouTube, Reddit, Twitter/X, etc.) load content
  // dynamically without a full page navigation.
  const observer = new MutationObserver(scheduleScan);
  const startObserving = () => {
    if (document.documentElement) {
      observer.observe(document.documentElement, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    }
  };
  if (document.documentElement) {
    startObserving();
  } else {
    document.addEventListener("DOMContentLoaded", startObserving);
  }

  // Belt-and-braces periodic re-check.
  setInterval(runScan, 2000);
})();
