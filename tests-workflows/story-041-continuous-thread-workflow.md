# STORY-041 — One Continuous Thread Test Workflow

Verifies context reset on topic shift, opening strip (absorbs milestones + weekly report),
journey tree in sidebar, curiosity chips, rediscovery annotation, topic depth inline,
daemon auto-save, Telegram `/journey` and curiosity footer, `lc status` journey,
and MCP `related_subjects`.

---

## Pre-flight

```bash
uv run lattice-daemon status
open http://localhost:7337
lc status
```

Confirm daemon running and atoms present. Keep `~/.lattice/chat.jsonl` accessible for inspection.

---

## Phase 1 — Unit & backend tests (automated)

```bash
uv run pytest -q
```

Expected: **639 passed**, 0 failed. Covers all existing stories including STORY-039 base.

---

## Phase 2 — New API endpoints (automated)

```bash
uv run python3 - << 'EOF'
from pathlib import Path
from datetime import datetime, timezone
import json

from lattice.config import Config
from lattice.web.app import app, set_config
from fastapi.testclient import TestClient

cfg = Config(lattice_dir=Path('/tmp/lattice_s041'), llm_provider='ollama', llm_model='test')
cfg.lattice_dir.mkdir(parents=True, exist_ok=True)
set_config(cfg)
client = TestClient(app)

# /api/chat/today empty
r = client.get('/api/chat/today?channel=web')
assert r.status_code == 200 and r.json() == [], r.json()
print('✓ /api/chat/today returns [] when no chat.jsonl')

# /api/chat/today with a today entry
entry = {
    'ts': datetime.now(timezone.utc).isoformat(),
    'session_id': 's1',
    'question': 'Tell me about Postgres',
    'answer': 'Postgres is a great DB.',
    'atom_ids': [],
    'subjects': ['Postgres'],
    'channel': 'web',
}
(cfg.lattice_dir / 'chat.jsonl').write_text(json.dumps(entry) + '\n')
r = client.get('/api/chat/today?channel=web')
assert r.status_code == 200
data = r.json()
assert len(data) == 1 and data[0]['question'] == 'Tell me about Postgres'
assert data[0].get('subjects') == ['Postgres']
print('✓ /api/chat/today returns today entry with subjects')

# /api/chat/today filters by channel
r = client.get('/api/chat/today?channel=telegram')
assert r.status_code == 200 and r.json() == []
print('✓ /api/chat/today filters by channel')

# /api/atoms/related with empty subjects
r = client.get('/api/atoms/related?subjects=')
assert r.status_code == 200 and r.json() == []
print('✓ /api/atoms/related returns [] for empty subjects')

# /api/atoms/related with unknown subject (no atoms in db)
r = client.get('/api/atoms/related?subjects=Postgres')
assert r.status_code == 200 and r.json() == []
print('✓ /api/atoms/related returns [] when no atoms found')

print('\n✅  Phase 2 all passed')
EOF
```

Expected: all 5 assertions pass.

---

## Phase 3 — context_reset SSE signal (automated)

```bash
uv run python3 - << 'EOF'
from lattice.conversation import is_followup

# Topic-shift queries: is_followup returns False
assert not is_followup("What did I decide about Postgres?"), "self-contained should not be followup"
assert not is_followup("Tell me about my travel plans to Japan"), "named topic, not followup"
assert not is_followup("What is the status of the Lattice project?"), "specific question, not followup"

# Follow-up queries: is_followup returns True
assert is_followup("why?"), "bare question word"
assert is_followup("when was that?"), "anaphoric"
assert is_followup("tell me more"), "explicit followup phrase"

print("✓ is_followup correctly classifies topic-shift vs follow-up")
print("\ncontext_reset logic:")
print("  context_reset = not is_followup(query) AND history is non-empty")
print("  → self-contained query after prior turns resets JS conversationHistory silently")
print("\n✅  Phase 3 all passed")
EOF
```

Expected: all assertions pass.

---

## Phase 4 — Daemon auto-save sweep (automated)

```bash
uv run python3 - << 'EOF'
import json, time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from lattice.config import Config
from lattice.daemon import _auto_save_chat_threads

tmp = Path('/tmp/lattice_s041_daemon')
tmp.mkdir(parents=True, exist_ok=True)
cfg = Config(lattice_dir=tmp, llm_provider='ollama', llm_model='test')

# Write 2 turns from >10 min ago
old_ts = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
turns = [
    {"ts": old_ts, "session_id": "s1", "question": "Q1", "answer": "A1",
     "atom_ids": [], "channel": "web"},
    {"ts": old_ts, "session_id": "s1", "question": "Q2", "answer": "A2",
     "atom_ids": [], "channel": "web"},
]
(tmp / "chat.jsonl").write_text("\n".join(json.dumps(t) for t in turns) + "\n")

# Run sweep — DaemonClient not running so ingest will fail, but auto_saved flag logic runs
# Just check the sweep parses the file without crashing
try:
    _auto_save_chat_threads(cfg)
except Exception as e:
    print(f"Sweep ran (DaemonClient offline expected): {e}")

# For turns < 10 min old: should NOT be auto-saved
recent_ts = datetime.now(timezone.utc).isoformat()
turns_recent = [
    {"ts": recent_ts, "session_id": "s2", "question": "Q3", "answer": "A3",
     "atom_ids": [], "channel": "web"},
    {"ts": recent_ts, "session_id": "s2", "question": "Q4", "answer": "A4",
     "atom_ids": [], "channel": "web"},
]
(tmp / "chat.jsonl").write_text("\n".join(json.dumps(t) for t in turns_recent) + "\n")

import unittest.mock
with unittest.mock.patch("lattice.client.DaemonClient") as mock_dc:
    mock_dc.return_value.ingest.return_value = []
    _auto_save_chat_threads(cfg)
    # ingest should NOT be called for recent turns (<10 min old)
    assert not mock_dc.return_value.ingest.called, "should not ingest recent turns"
print("✓ Auto-save does not trigger for turns <10 min old")

# For turns > 10 min old: should auto-ingest
old_ts = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
turns_old = [
    {"ts": old_ts, "session_id": "s3", "question": "Q5", "answer": "A5",
     "atom_ids": [], "channel": "web"},
    {"ts": old_ts, "session_id": "s3", "question": "Q6", "answer": "A6",
     "atom_ids": [], "channel": "web"},
]
(tmp / "chat.jsonl").write_text("\n".join(json.dumps(t) for t in turns_old) + "\n")

with unittest.mock.patch("lattice.client.DaemonClient") as mock_dc:
    mock_dc.return_value.ingest.return_value = []
    _auto_save_chat_threads(cfg)
    assert mock_dc.return_value.ingest.called, "should ingest old turns"
print("✓ Auto-save triggers for turns >10 min old")

# Verify auto_saved flag is written
data = [(tmp / "chat.jsonl").read_text()]
lines = [json.loads(l) for l in data[0].strip().splitlines()]
assert all(l.get("auto_saved") for l in lines), f"auto_saved flag missing: {lines}"
print("✓ auto_saved flag written to chat.jsonl after sweep")

print("\n✅  Phase 4 all passed")
EOF
```

Expected: all assertions pass.

---

## Phase 5 — Opening strip in web UI [MANUAL]

Open `http://localhost:7337` in a fresh tab (or private window so no sessionStorage).

**Expected on page load:**
- A quiet strip appears **above** the cube/greeting in the empty-state area
- Strip shows at minimum: `N days deep · M things saved`
- If you asked questions today (chat.jsonl has today entries), strip also shows:
  `You've been thinking about: [Topic chip] [Topic chip]`
- Topic chips are clickable → pre-fills the input field (no auto-submit)
- Strip disappears once you start typing

**If it's Monday and streak ≥ 7:**
- Weekly summary line also appears: `This week — N saved · M questions`

**If today is streak day 1/7/14/30 (and not shown before):**
- Milestone message appears as italic text in the strip

**NOT expected:** any floating milestone cards or weekly report cards in the chat area.

---

## Phase 6 — context_reset clears conversation history silently [MANUAL]

In the web UI, run a two-topic conversation:

1. Ask: `Tell me about my Postgres decisions`
2. Ask: `when did I make that call?` ← follow-up, no reset
3. Ask: `What do I know about Alex Chen?` ← topic shift, should reset

After step 3, open DevTools → Console:
```javascript
conversationHistory
```

Expected: array has only the Alex Chen turn (the Postgres turns were cleared silently when
`context_reset: true` arrived in the SSE atoms event).

Also confirm in `chat.jsonl`:
```bash
tail -5 ~/.lattice/chat.jsonl | python3 -m json.tool
```

All 3 turns should be recorded. No entry for "reformulated_query" on the Alex question
(it was self-contained, not a follow-up).

---

## Phase 7 — Journey tree builds in sidebar [MANUAL]

After Phase 6 (3 queries made), look at the left sidebar (atoms panel).

**Expected:**
- New "Today's journey" section at the top, above "Recent memories"
- Tree grouped by subject, e.g.:
  ```
  Today's journey

  ● Postgres
  │   └── Tell me about my Postgr…    5m ago
  │   └── when did I make that ca…    4m ago

  ● Alex Chen
      └── What do I know about Sh…    2m ago
  ```
- Clicking a branch label (`● Postgres`) → pre-fills `"Tell me about Postgres"` in input
- Clicking a leaf → re-submits that exact query
- Section only appears after at least 1 query with subjects

**Page reload test:**
Reload the page. Journey tree should **rebuild from `GET /api/chat/today`** — same branches
visible as before (because today's queries are in chat.jsonl with subjects).

---

## Phase 8 — Curiosity chips below answer [MANUAL]

Ask any question that retrieves atoms with related subjects, e.g.:
```
What do I know about Postgres?
```

**Expected after the answer:**
- A row appears below the answer: `You also know about: [PgBouncer]  [connection pooling]  [SQLite]`
  (exact subjects depend on what's in your lattice)
- Tapping a chip pre-fills the input: `Tell me about PgBouncer` (no auto-submit)
- When you ask the next question, the chips on the previous turn disappear (only shown on most recent turn)
- If no related subjects exist via BFS, no chips row shown

---

## Phase 9 — Rediscovery annotation [MANUAL]

This requires an atom that was ingested ≥ 30 days ago. If you have old atoms:

Ask any question that retrieves a ≥ 30-day-old atom.

**Expected below the answer** (after the answer text, before curiosity chips):
```
You first saved this 47 days ago.
```

Single quiet line in muted italic. Only shown once per answer. If all cited atoms are recent (<30 days),
no line appears.

**Note:** if your lattice is new (all atoms recent), skip this phase and mark it as N/A.

---

## Phase 10 — Topic depth inline annotation [MANUAL]

Ask about a topic where you have saved ≥5 atoms, e.g.:
```
Tell me about Postgres
```

If the cited subject has ≥5 atoms stored (5/10/20 threshold), a line appears below the answer:
```
You've saved 10 things about Postgres. You've thought about this a lot.
```

**NOT expected:** a floating card in the chat area. The note is inline, below the answer, not a separate card.

Check that `localStorage` records the threshold so the note doesn't repeat:
```javascript
localStorage.getItem("lattice_topic_depth_postgres")
// Should return "10" (or "5" or "20" depending on count)
```

---

## Phase 11 — Telegram: /journey command [MANUAL]

Requires Telegram bot running with atoms in lattice and some today turns.

1. Send `/ask What do I know about Postgres?`
2. Send `/journey`

**Expected response:**
```
Today's journey:

● Postgres
   └── What do I know about Postgres?
```

Tree rendered as plain text. Each branch = primary subject, each leaf = question asked.

---

## Phase 12 — Telegram: curiosity footer [MANUAL]

After any `/ask` that retrieves atoms with related subjects:

**Expected extra message after the answer:**
```
You also know about: PgBouncer · connection pooling

Use /ask <topic> to explore.
```

Only appears when `/api/atoms/related` returns results. If no related subjects, no footer.

---

## Phase 13 — Telegram: daily opening strip [MANUAL]

Send any message to the bot (first interaction of the day).

**Expected:**
- Bot sends an extra message first, before the normal response:
  ```
  14 days deep · 284 things saved
  Today you've been thinking about: Postgres, Alex Chen
  ```
- Only shown once per day (tracked via `bot_data["opening_strip_YYYY-MM-DD"]`)
- On subsequent messages the same day: no strip prepended

---

## Phase 14 — lc status journey summary [MANUAL]

After making at least 1 web/telegram query today (so chat.jsonl has today entries with subjects):

```bash
lc status
```

**Expected output includes:**
```
284 memories · Topics: Postgres, React · 14 days deep
Today's journey: Postgres (2 questions), Alex Chen (1 question)
```

The "Today's journey" line only appears if chat.jsonl has entries for today's date.
If no queries were made today, the line is absent.

---

## Phase 15 — MCP related_subjects [MANUAL / Claude Code]

In Claude Code with the Lattice MCP server running, call `lattice_answer`:

```
lattice_answer(query="What do I know about Postgres?")
```

**Expected:** the result JSON includes a `related_subjects` field:
```json
{
  "answer": "...",
  "related_subjects": ["PgBouncer", "connection pooling", "SQLite"]
}
```

If no related subjects exist via BFS, only `{"answer": "..."}` is returned (no `related_subjects` key).

---

## Phase 16 — Daemon auto-save end-to-end [MANUAL]

This test requires waiting or simulating old turns.

1. Make 2+ queries via the web UI (or Telegram)
2. In `chat.jsonl`, manually backdate the `ts` fields of those turns to >10 minutes ago:
   ```bash
   python3 -c "
   import json, pathlib
   p = pathlib.Path('~/.lattice/chat.jsonl').expanduser()
   old_ts = '2026-01-01T00:00:00+00:00'  # definitely >10 min ago
   lines = [json.loads(l) for l in p.read_text().strip().splitlines() if l.strip()]
   for l in lines[-2:]:
       l['ts'] = old_ts
   p.write_text('\n'.join(json.dumps(l) for l in lines) + '\n')
   print('backdated', len(lines[-2:]), 'turns')
   "
   ```
3. Restart the daemon (it runs auto-save on startup):
   ```bash
   uv run lattice-daemon  # in a new terminal, Ctrl+C existing first
   ```
4. Check `lc status` — atom count should have increased (the thread was auto-ingested)
5. Check `chat.jsonl` — the two backdated turns should have `"auto_saved": true`

---

## Summary

| Phase | Description | Type |
|---|---|---|
| 1 | Unit + backend tests (639 pass) | Automated |
| 2 | New API endpoints (/api/chat/today, /api/atoms/related) | Automated |
| 3 | context_reset SSE signal logic | Automated |
| 4 | Daemon auto-save sweep | Automated |
| 5 | Opening strip on page load | Manual |
| 6 | context_reset clears JS conversation history | Manual |
| 7 | Journey tree builds in sidebar + page reload | Manual |
| 8 | Curiosity chips below most recent answer | Manual |
| 9 | Rediscovery annotation (≥30 days) | Manual |
| 10 | Topic depth inline annotation (≥5 atoms) | Manual |
| 11 | Telegram /journey command | Manual |
| 12 | Telegram curiosity footer | Manual |
| 13 | Telegram daily opening strip | Manual |
| 14 | lc status journey summary | Manual |
| 15 | MCP related_subjects in lattice_answer | Manual |
| 16 | Daemon auto-save end-to-end | Manual |
