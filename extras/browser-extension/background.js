const LATTICE_URL = "http://localhost:7337";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "save-to-lattice",
    title: "Save to Lattice",
    contexts: ["selection"],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== "save-to-lattice") return;
  const text = info.selectionText?.trim();
  if (!text) return;
  saveToLattice(text, tab.url, tab.title);
});

// Content script posts selected text via message (for keyboard shortcut path)
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "save" && msg.text) {
    saveToLattice(msg.text, msg.url, msg.title);
  }
});

async function saveToLattice(text, url, title) {
  try {
    const resp = await fetch(`${LATTICE_URL}/api/ingest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, url, title }),
    });
    const data = await resp.json();
    if (data.ok) {
      const n = data.atom_ids?.length ?? 0;
      notify("Saved to Lattice", n > 0 ? `${n} memory atom${n === 1 ? "" : "s"} added` : "Already in memory");
    } else {
      notify("Lattice error", data.error || "Unknown error");
    }
  } catch {
    notify("Lattice unreachable", "Is the daemon running? Try: uv run lattice-daemon");
  }
}

function notify(title, message) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/icon48.png",
    title,
    message,
  });
}
