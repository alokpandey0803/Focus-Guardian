chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg && msg.type === "FG_CLOSE_TAB" && sender.tab && typeof sender.tab.id === "number") {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icon128.png",
      title: "🚫 Blocked Content Closed",
      message: `"${msg.keyword}" was detected on the page.\n${msg.quote}`,
    });
    chrome.tabs.remove(sender.tab.id).catch(() => {});
  }
});
