const dot = document.getElementById("status-dot");
const label = document.getElementById("status-label");
const countEl = document.getElementById("atom-count");

fetch("http://localhost:7337/health")
  .then((r) => r.json())
  .then((d) => {
    if (d.ok) {
      dot.className = "green";
      label.textContent = "daemon running";
    } else {
      throw new Error();
    }
  })
  .catch(() => {
    dot.className = "red";
    label.textContent = "daemon offline";
  });

fetch("http://localhost:7337/api/usage/summary")
  .then((r) => r.json())
  .then((d) => {
    if (d.atom_count != null) countEl.textContent = `${d.atom_count} memories stored`;
  })
  .catch(() => {});

const autoSaveEl = document.getElementById("auto-save-status");
fetch("http://localhost:7337/api/auto-save/status")
  .then((r) => r.json())
  .then((d) => {
    if (d.running) autoSaveEl.style.display = "block";
  })
  .catch(() => {});
