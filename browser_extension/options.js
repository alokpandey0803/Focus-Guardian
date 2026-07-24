const enabledToggle = document.getElementById("enabledToggle");
const adultContentToggle = document.getElementById("adultContentToggle");
const defaultList = document.getElementById("defaultList");
const customList = document.getElementById("customList");
const newKeyword = document.getElementById("newKeyword");
const addBtn = document.getElementById("addBtn");
const status = document.getElementById("status");

defaultList.textContent = DEFAULT_KEYWORDS.join(", ");

function showStatus(msg) {
  status.textContent = msg;
  setTimeout(() => (status.textContent = ""), 1500);
}

function renderCustom(list) {
  customList.innerHTML = "";
  list.forEach((kw, i) => {
    const li = document.createElement("li");
    const span = document.createElement("span");
    span.textContent = kw;
    const btn = document.createElement("button");
    btn.textContent = "Remove";
    btn.onclick = () => {
      const updated = list.filter((_, idx) => idx !== i);
      chrome.storage.sync.set({ customKeywords: updated }, () => {
        renderCustom(updated);
        showStatus("Removed.");
      });
    };
    li.appendChild(span);
    li.appendChild(btn);
    customList.appendChild(li);
  });
}

function load() {
  chrome.storage.sync.get(["enabled", "customKeywords", "blockAdultContent"], (data) => {
    enabledToggle.checked = data.enabled !== false;
    adultContentToggle.checked = data.blockAdultContent === true; // default: off
    renderCustom(Array.isArray(data.customKeywords) ? data.customKeywords : []);
  });
}

enabledToggle.addEventListener("change", () => {
  chrome.storage.sync.set({ enabled: enabledToggle.checked }, () => {
    showStatus(enabledToggle.checked ? "Enabled." : "Disabled.");
  });
});

adultContentToggle.addEventListener("change", () => {
  chrome.storage.sync.set({ blockAdultContent: adultContentToggle.checked }, () => {
    showStatus(adultContentToggle.checked ? "Adult content blocking on." : "Adult content blocking off.");
  });
});

addBtn.addEventListener("click", () => {
  const val = newKeyword.value.trim().toLowerCase();
  if (!val) return;
  chrome.storage.sync.get(["customKeywords"], (data) => {
    const list = Array.isArray(data.customKeywords) ? data.customKeywords : [];
    if (list.includes(val)) {
      showStatus("Already added.");
      return;
    }
    const updated = [...list, val];
    chrome.storage.sync.set({ customKeywords: updated }, () => {
      renderCustom(updated);
      newKeyword.value = "";
      showStatus("Added.");
    });
  });
});

newKeyword.addEventListener("keydown", (e) => {
  if (e.key === "Enter") addBtn.click();
});

load();
