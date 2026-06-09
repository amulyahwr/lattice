// Keyboard shortcut: Alt+Shift+S saves current selection
document.addEventListener("keydown", (e) => {
  if (e.altKey && e.shiftKey && e.code === "KeyS") {
    const text = window.getSelection()?.toString().trim();
    if (!text) return;
    chrome.runtime.sendMessage({
      type: "save",
      text,
      url: location.href,
      title: document.title,
    });
  }
});
