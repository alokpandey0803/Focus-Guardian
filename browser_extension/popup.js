chrome.storage.sync.get(["enabled"], (data) => {
  const on = data.enabled !== false;
  const el = document.getElementById("stateText");
  el.textContent = on ? "Active" : "Disabled";
  el.className = on ? "on" : "off";
});

document.getElementById("openOptions").addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});
