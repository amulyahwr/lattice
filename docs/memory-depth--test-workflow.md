# STORY-030 Test Workflow — Memory Depth

Verifies streak reframe, grace day, milestone cards, and cross-channel streak display.

---

## Pre-flight

```bash
lattice-start
open http://localhost:7337
```

Make sure you have at least one recall query recorded today so the streak is active. If starting fresh:

```bash
curl -s -X POST http://localhost:7337/api/answer \
  -H "Content-Type: application/json" \
  -d '{"question": "what do I prefer?"}' | python3 -m json.tool
```

---

## Phase 1 — Web UI: Streak badge label

After making at least one recall query, reload `http://localhost:7337`.

**Expected badge (Day 1):**
```
1 day deep
```

**Expected badge (Day 5):**
```
5 days deep
```

**Expected badge (Day 30+):**
```
30 days deep 🎯
```

**Tooltip on hover:**
```
Consecutive days you've recalled something. Goal: 30 days deep.
```

**Verify:**
- Badge says "N days deep" — NOT "Day N"
- Singular "day" at streak=1, plural "days" at streak≥2
- Badge is hidden when streak=0 and grace day is not active

---

## Phase 2 — Web UI: Grace day

**Best tested naturally:** come back the next morning before making any query. If yesterday had at least one recall, the badge will show `N days deep · rest day`.

To simulate it manually, you need today's `usage.jsonl` entries removed AND a yesterday entry present. This overwrites real usage data — only do this in a test setup:

```bash
TODAY=$(date -u +%Y-%m-%d)
YESTERDAY=$(date -u -v-1d +%Y-%m-%d 2>/dev/null || date -u -d "yesterday" +%Y-%m-%d)

# Keep only non-today entries, add a fake yesterday if none exists
grep -v "\"$TODAY" ~/.lattice/usage.jsonl > /tmp/usage_no_today.jsonl || true
echo "{\"ts\":\"${YESTERDAY}T12:00:00+00:00\",\"query_hash\":\"test\",\"selection_ms\":10,\"synthesis_ms\":100,\"atom_count\":1,\"channel\":\"web\"}" >> /tmp/usage_no_today.jsonl
cp ~/.lattice/usage.jsonl ~/.lattice/usage.jsonl.bak  # back up first
cp /tmp/usage_no_today.jsonl ~/.lattice/usage.jsonl
```

> **Note:** Adding only a yesterday entry while today still has entries gives streak=2 (both days counted) — NOT a grace day. Grace day only activates when today has zero entries.

Reload `http://localhost:7337` without making a new query.

**Expected (if yesterday had queries and no grace used this week):**
```
N days deep · rest day
```

- Streak count holds at yesterday's value
- "rest day" label appears
- Badge still visible — streak not reset

**Verify:**
- Make a new query today → badge updates to normal "N days deep" (grace day consumed)

---

## Phase 3 — Web UI: Milestone card

Two things are required for a milestone card to show:
1. Your **streak equals a milestone day** (1, 7, 14, or 30)
2. The **localStorage key is not set** (card shown at most once ever)

### Step 1 — Reset the localStorage key

In the browser console (`Cmd+Option+J` on Mac):

```javascript
// Reset ALL milestone keys so any milestone can show again
['1','7','14','30'].forEach(d => localStorage.removeItem(`lattice_milestone_shown_${d}`));
```

### Step 2 — Set the streak to a milestone value

Your current streak is whatever `usage.jsonl` says. To hit **Day 7**, add 6 consecutive fake past-day entries:

```bash
for i in 1 2 3 4 5 6; do
  D=$(python3 -c "from datetime import date, timedelta; print((date.today() - timedelta(days=$i)).isoformat())")
  echo "{\"ts\":\"${D}T12:00:00+00:00\",\"query_hash\":\"fake\",\"selection_ms\":10,\"synthesis_ms\":100,\"atom_count\":1,\"channel\":\"web\"}" >> ~/.lattice/usage.jsonl
done
```

For **Day 1**: your streak is already ≥1 if you've queried today — just clear the key (Step 1) and ask something.

### Step 3 — Make a recall query

Type a question in the web UI and press Enter. The milestone card appears **above the answer** once the response completes.

**Expected:**
- Day 1: *"First recall. Good start."*
- Day 7: *"A week in. Lattice is starting to know you."*
- Day 14: *"Two weeks of asking and remembering. You have N things stored — this is becoming real."*
- Day 30: *"30 days. You've built something here. Try going a week without it — you'll know it's working."*

The card has a `✕` dismiss button. After dismissal, the localStorage key is set and the card will never show again for that milestone day.

**Cube animation:** the logo briefly bounces when the milestone card fires — triggered once per browser session.

**Verify non-milestone day (e.g. Day 5):**
Run the bash loop above with `for i in 1 2 3 4` (4 past days = Day 5 streak today). Clear keys, make a query — no card, no animation.

---

## Phase 4 — Verify streak via API

```bash
curl http://localhost:7337/api/usage/summary | python3 -m json.tool
```

**Expected fields:**
```json
{
    "today": 1,
    "last_7_days": 1,
    "avg_latency_ms": 0,
    "streak": 1,
    "grace_day_active": false,
    "atom_count": 12
}
```

- `grace_day_active: true` if today has no queries but yesterday did
- `atom_count` reflects current non-superseded atoms

---

## Phase 5 — Telegram `/status`

```
/status
```

**With streak active:**
```
12 memories · 3 days deep
```

**On grace day (missed today, queried yesterday):**
```
12 memories · 3 days deep · rest day
```

**No streak (never recalled):**
```
12 memories
```

- Singular "day deep" at streak=1, plural "days deep" at streak≥2

---

## Phase 6 — Telegram milestone

On a milestone day (Day 1, 7, 14, or 30), send any recall question.

**Expected:**
- Milestone message appears as a separate reply BEFORE the answer
- Day 14 message includes current atom count
- Only shown once per bot session (not every message)

---

## Phase 7 — `lc status`

```bash
lc status
```

**Expected:**
```
12 memories · Topics: coffee, hiking, travel · 3 days deep
```

- Streak appended after topics
- No streak line when streak=0
- Topics section omitted when no subjects stored

---

## Pass criteria

| Check | Pass if |
|---|---|
| Badge says "N days deep" not "Day N" | ✅ new label |
| Singular at 1, plural at 2+ | ✅ grammar correct |
| Badge hidden at streak=0, no grace | ✅ not visible |
| Grace day shows "· rest day" | ✅ streak holds, rest day appended |
| Two missed days → streak resets to 0 | ✅ no badge |
| Milestone card appears on Day 1/7/14/30 | ✅ warm card, correct message |
| Day 14 card shows atom count | ✅ number in message |
| Milestone card dismissed permanently | ✅ localStorage key set, card gone on reload |
| Cube animation fires on milestone | ✅ visible bounce |
| No card on non-milestone days | ✅ silent |
| `/api/usage/summary` has grace_day_active + atom_count | ✅ new fields present |
| Telegram `/status` shows "N days deep" | ✅ with grace label when active |
| Telegram milestone prepended before answer | ✅ separate message |
| `lc status` shows streak | ✅ "N days deep" appended |
