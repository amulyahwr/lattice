# Cross-Channel Test Workflow

Verifies that all capture and recall functionality works consistently across every Lattice channel. All channels share the same `~/.lattice` store.

---

## Pre-flight

```bash
lattice-start
open http://localhost:7337
```

Confirm daemon and Telegram bot are running:

```bash
launchctl list | grep lattice
```

Expected: both `dev.lattice.daemon` and `dev.lattice.telegram` listed with exit code 0.

---

## Phase 1 — Telegram: Capture + Recall

**Capture:**
Send a plain statement to the bot:
```
I prefer window seats on flights
```

Expected reply:
```
Saved. 1 new thing added to your memory.
```

**Recall:**
Send a question:
```
What do I prefer when flying?
```

Or use `/ask`:
```
/ask what do I prefer when flying?
```

Expected: synthesised answer citing the atom you just saved.

---

## Phase 2 — Web UI: Capture (Save session) + Recall

**Recall:**
Type a question in the input bar and press Enter. Answer should stream in with source citations.

**Session capture:**
Click the **Save session** button in the header after at least one Q&A turn. Expected: button shows "✓ Saved" briefly.

---

## Phase 3 — `lc` CLI: Capture

```bash
lc "decided to use Postgres for the side project"
```

Expected:
```
Saved. 1 new thing added to your memory.
```

**Status check:**
```bash
lc status
```

Expected: `N memories · Topics: ... · N days deep`

---

## Phase 4 — Claude Code (MCP): Capture + Recall

In a Claude Code session, use the MCP tools directly:

**Capture:**
```
lattice_ingest: source="I prefer mechanical keyboards with linear switches", metadata.source="user", metadata.source_id="claude-code", metadata.observed_at=<now>
```

**Recall:**
```
lattice_answer: query="what keyboard do I prefer?"
```

**Status:**
```
lattice_status
```

Expected JSON: `{"count": N, "streak": N, "grace_day_active": false}`

---

## Phase 5 — Inbox drop: Capture

Drop a markdown file into the inbox:

```bash
echo "# Meeting notes\nDecided to move standup to 9am." > ~/.lattice/inbox/standup.md
```

Wait ~5 seconds. Check that the file moved to `processed/`:

```bash
ls ~/.lattice/processed/ | grep standup
```

Confirm the atom was created:

```bash
lc status
```

Count should have increased by at least 1.

---

## Phase 6 — Cross-channel recall consistency

After capturing from multiple channels (Phases 1–5), recall the same fact from a different channel:

- Capture via `lc`: `lc "I take my coffee black"`
- Recall via Telegram: `/ask how do I take my coffee?`
- Recall via Web UI: type "how do I take my coffee?"
- Recall via Claude Code: `lattice_answer: query="how do I take my coffee?"`

All channels should return the same atom in their answer.

---

## Phase 7 — Session end capture

**Telegram `/save`:**
After a few captures/recalls in the Telegram session, send:
```
/save
```

Expected: confirmation that the session was saved as a memory chunk.

**Web UI Save session:**
Click the **Save session** button — should be enabled after at least one Q&A.

---

## Pass criteria

| Check | Pass if |
|---|---|
| Telegram capture → atom stored | ✅ `lc status` count increases |
| Telegram recall → synthesised answer | ✅ answer cites stored atom |
| Web UI recall → streaming answer | ✅ SSE stream with citations |
| Web UI Save session → atom stored | ✅ count increases, session saved |
| `lc` capture → atom stored | ✅ "Saved. N new things" |
| `lc status` → count + topics + streak | ✅ all three shown |
| MCP `lattice_ingest` → atom stored | ✅ atom_ids returned |
| MCP `lattice_answer` → answer | ✅ grounded in lattice atoms |
| MCP `lattice_status` → count + streak | ✅ JSON with streak |
| Inbox drop → processed within 5s | ✅ file in processed/ |
| Cross-channel recall consistency | ✅ same atom across channels |
| Telegram `/save` → session captured | ✅ confirmation reply |
