# Browser Extension Workflow — Save to Lattice

Verifies the Chrome browser extension captures selected text from any webpage and sends it to the local Lattice daemon.

---

## Pre-flight

Daemon must be running and extension must be loaded in Chrome.

```bash
uv run lattice-daemon          # start daemon if not already running
uv run lattice-daemon status   # confirm: {"ok": true}
open http://localhost:7337     # confirm web UI is up
```

---

## Phase 1 — Load extension in Chrome  *(you do this)*

1. Open Chrome → address bar → `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked**
4. Select the folder: `extras/browser-extension/`

Extension should appear in the list with a Lattice icon.

**Pin it to the toolbar:**
Click the puzzle-piece icon in the Chrome toolbar → pin **Lattice**.

**Verify popup:**
Click the Lattice icon in the toolbar.
- Status dot should be **green** with label "daemon running"
- Memory count should show e.g. "47 memories stored"

If dot is red: daemon is not running. Run `uv run lattice-daemon`.

---

## Phase 2 — Right-click capture  *(you do this)*

Open any webpage with text — e.g. a Wikipedia article, GitHub README, or Hacker News post.

1. Select a sentence or paragraph
2. Right-click the selection
3. Click **Save to Lattice**

**Expected:** Chrome notification appears:
```
Saved to Lattice
3 memory atoms added
```

**Verify it landed:**
```bash
lc status     # count should have increased
```

Or open `http://localhost:7337` → Recent memories panel should show the new atoms with the page URL as source.

**Re-save the same text:**
Select the same text → right-click → Save to Lattice.

Expected notification:
```
Saved to Lattice
Already in memory
```

---

## Phase 3 — Keyboard shortcut  *(you do this)*

1. Select text on any webpage
2. Press **Option (⌥) + Shift (⇧) + S**

Expected: same notification as Phase 2.

**Without a selection:**
Press ⌥+⇧+S with nothing selected → no notification, no action.

---

## Phase 4 — Source metadata in citations  *(you do this)*

After capturing text from a webpage, recall it via the web UI or Telegram.

Open `http://localhost:7337` and ask something related to what you saved.

**Expected:** answer cites the page URL as the source in the sources section, and the page title appears as the citation label (e.g. `[Wikipedia — Retrieval-augmented generation][src:https://en.wikipedia.org/...]`).

---

## Phase 5 — Daemon offline behaviour  *(you do this)*

1. Stop the daemon: `launchctl unload ~/Library/LaunchAgents/dev.lattice.daemon.plist` (or kill the process)
2. Select text on a page → right-click → Save to Lattice

Expected notification:
```
Lattice unreachable
Is the daemon running? Try: uv run lattice-daemon
```

Restart daemon: `uv run lattice-daemon` — then retry. Should succeed.

---

## Pass criteria

| Check | Pass if |
|---|---|
| Extension loads in Chrome without errors | ✅ appears in chrome://extensions |
| Popup shows green dot + memory count | ✅ daemon connected |
| Right-click → Save to Lattice appears on selected text | ✅ context menu item visible |
| Capture notifies with atom count | ✅ "N memory atoms added" |
| Re-capture same text notifies "Already in memory" | ✅ dedup working |
| Alt+Shift+S shortcut captures selected text | ✅ notification appears |
| Captured atoms appear in web UI Recent memories | ✅ source_id = page URL |
| Page title appears as citation label in recall | ✅ source_title stored |
| Daemon offline → clear error notification | ✅ not a silent failure |

---

## Troubleshooting

**Context menu doesn't appear:**
Check that text is actually selected before right-clicking. The menu item only shows on `selection` context.

**Notification doesn't appear:**
Chrome may have notifications blocked for extensions. Go to `chrome://settings/content/notifications` and check extension permissions.

**"Lattice unreachable" even with daemon running:**
Check daemon is on port 7337: `curl http://localhost:7337/health` should return `{"ok":true}`. If using a custom `LATTICE_WEB_PORT`, update `LATTICE_URL` in `background.js`.

**Extension not updating after code change:**
Go to `chrome://extensions` → click the reload icon (↺) on the Lattice card.
