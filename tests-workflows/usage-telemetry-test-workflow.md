# STORY-013 Test Workflow — Usage Telemetry + Streak

Verifies that recall queries are tracked across all channels and the streak is computed correctly.

---

## Pre-flight

```bash
lattice-start
open http://localhost:7337
```

---

## Step 1 — Trigger recall from each channel

**Web UI:** ask any question in the chat → answer streams in

**Telegram:** send a question (auto-detected as recall) or `/ask <question>`

**Claude Code:** ask anything that triggers `lattice_answer`

---

## Step 2 — Check summary endpoint

```bash
curl http://localhost:7337/api/usage/summary | python3 -m json.tool
```

Expected output:
```json
{
    "today": 3,
    "last_7_days": 3,
    "avg_latency_ms": 80,
    "streak": 1,
    "grace_day_active": false,
    "atom_count": 12
}
```

- `today` should match the number of recall queries made across all channels
- `streak` should be 1 (first day of use)
- `grace_day_active` is true only when today has 0 queries but yesterday had some
- `atom_count` is total non-superseded atoms

---

## Step 3 — Check web UI header

Reload `http://localhost:7337` — **1 day deep** badge should appear in the header. Badge only appears after at least one query. On grace days it shows `"N days deep · rest day"`.

---

## Step 4 — Verify `usage.jsonl` directly

```bash
cat ~/.lattice/usage.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    r = json.loads(line)
    print(r.get('ts','')[:10], r.get('channel', r.get('type','?')))
" | head -20
```

Each query record has: `ts`, `query_hash` (SHA-1, not plaintext), `selection_ms`, `synthesis_ms`, `atom_count`, `channel`.

---

## Step 5 — Verify channel attribution

Make one query from each channel, then:

```bash
cat ~/.lattice/usage.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    r = json.loads(line.strip())
    if r.get('type') == 'grace_day_used': continue
    print(r['channel'], r['ts'][:10])
"
```

Should show entries for `web`, `telegram`, and `mcp`.

---

## Step 6 — Streak continuity (requires 2 days)

Come back tomorrow, make one query from any channel, then recheck:

```bash
curl http://localhost:7337/api/usage/summary | python3 -m json.tool
```

`streak` should show `2`. Web UI header should show **2 days deep**.

---

## Pass criteria

| Check | Pass if |
|---|---|
| `today` count matches actual recall queries | ✅ correct count |
| `streak` shows N days correctly | ✅ matches consecutive days |
| `grace_day_active` true when today empty + yesterday had queries | ✅ shows `· rest day` in badge |
| `atom_count` matches `lc status` count | ✅ same number |
| `channel` field correct per source | ✅ `web` / `telegram` / `mcp` |
| Web UI shows "N days deep" badge after first query | ✅ visible in header |
| `usage.jsonl` has no raw question text | ✅ SHA-1 hashes only |
| Capture-only actions (`lc "..."`, inbox drop) NOT counted | ✅ absent from `usage.jsonl` |
| `avg_latency_ms` non-zero after Telegram `/ask` | ✅ real latency recorded |

---

## Notes

- `avg_latency_ms = 0` for web UI queries is expected — streaming synthesis is lazy and cannot be timed server-side
- Telegram `/ask` and Claude Code `lattice_answer` record real `synthesis_ms` values
- Streak resets to 0 if today has no queries and grace day is not active
- Grace day: one free missed day per 7-day window before streak resets
- All timestamps stored in UTC; streak calculation uses UTC date to avoid timezone drift
