# STORY-031 Test Workflow — Weekly Memory Report + Topic Depth Cards

Verifies the weekly report card, topic depth notifications, and cross-channel delivery.

---

## Pre-flight

```bash
lattice-start
open http://localhost:7337
```

---

## Phase 1 — API: Weekly report data

```bash
curl http://localhost:7337/api/usage/weekly | python3 -m json.tool
```

**Expected:**
```json
{
    "atoms_this_week": 3,
    "recalls_this_week": 12,
    "topics_this_week": 2,
    "new_topics": ["travel"],
    "top_topic": "coffee",
    "streak": 2
}
```

- `atoms_this_week`: atoms ingested in the last 7 days
- `recalls_this_week`: recall queries in `usage.jsonl` from last 7 days
- `new_topics`: subjects that appear this week but never before
- `top_topic`: most frequently queried subject this week

---

## Phase 2 — API: Topic depth

```bash
# Replace "coffee" with a subject you have stored
curl "http://localhost:7337/api/topic/depth?subject=coffee" | python3 -m json.tool
```

**Expected:**
```json
{
    "subject": "coffee",
    "count": 3
}
```

- Count reflects non-superseded atoms only
- Case-insensitive: `"Coffee"` and `"coffee"` return the same count

---

## Phase 3 — Web UI: Topic depth card

Topic depth cards appear after a recall query when a cited subject has ≥5 atoms.

### Setup: get a subject to 5+ atoms

```bash
for i in 1 2 3 4 5; do
  lc "coffee fact $i"
done
```

Wait a few seconds for the daemon to process, then:

```bash
curl "http://localhost:7337/api/topic/depth?subject=coffee" | python3 -m json.tool
# count should be ≥ 5
```

### Clear the localStorage key so the card can show:

```javascript
// In browser console:
localStorage.removeItem('lattice_topic_depth_coffee');
```

### Ask a recall question that retrieves the coffee atom:

Type "what do I prefer about coffee?" in the web UI and press Enter.

**Expected after the answer loads:**
- A card appears below the answer with an accent left border:
  - *"You've saved 5 things about coffee. That's a topic you know well."*
  - At 10+: *"You've thought about this a lot."*
  - At 20+: *"This is one of the things you know best."*
- Card has a `✕` dismiss button
- Card does NOT appear again after dismissal (localStorage key set)

---

## Phase 4 — Web UI: Weekly report card

The report card only appears on **Mondays** when **streak ≥ 7**. To test it now:

### Step 1 — Fake 6 past days in usage.jsonl (to reach streak 7):

```bash
for i in 1 2 3 4 5 6; do
  D=$(python3 -c "from datetime import date, timedelta; print((date.today() - timedelta(days=$i)).isoformat())")
  echo "{\"ts\":\"${D}T12:00:00+00:00\",\"query_hash\":\"fake\",\"selection_ms\":10,\"synthesis_ms\":0,\"atom_count\":1,\"channel\":\"web\"}" >> ~/.lattice/usage.jsonl
done
```

### Step 2 — Clear the weekly localStorage key:

```javascript
// In browser console — get current ISO week key:
const d = new Date();
const jan4 = new Date(d.getFullYear(), 0, 4);
const wk = Math.ceil(((d - jan4) / 86400000 + jan4.getDay() + 1) / 7);
const key = `lattice_weekly_report_${d.getFullYear()}-W${String(wk).padStart(2,'0')}`;
console.log('Clearing:', key);
localStorage.removeItem(key);
```

### Step 3 — Temporarily set the day to Monday in the endpoint check:

The card is gated on `getDay() === 1` (Monday) in JavaScript. To test on any day, temporarily override in the browser console:

```javascript
// Patch Date.prototype.getDay to return 1 (Monday) for this session:
const _orig = Date.prototype.getDay;
Date.prototype.getDay = function() { return 1; };
// Now reload the page — weekly report should appear
// Restore after test:
Date.prototype.getDay = _orig;
```

Or just wait until Monday morning and reload — the card will show automatically if streak ≥ 7.

**Expected card content:**
```
This week
3 things saved · 12 questions asked · 2 topics
Most on your mind: coffee
Something new: travel
7 days deep.                    [✕]
```

---

## Phase 5 — Telegram: Topic depth after capture

Send 5 short capture messages on the same topic:

```
dog fact 1
dog fact 2
dog fact 3
dog fact 4
dog fact 5
```

After the 5th message (or whichever crosses the threshold):

**Expected reply after confirmation:**
```
You've saved 5 things about dog. That's a topic you know well.
```

- Only sent once per subject per bot session (uses `bot_data`)
- Threshold messages: 5 → "know well", 10 → "thought about a lot", 20 → "know best"

---

## Phase 6 — Telegram: Weekly summary on Monday

On Monday, send any message to the bot (capture or recall).

**Expected first reply (if streak ≥ 7):**
```
This week — 3 things saved, 12 questions asked, 2 topics. Most on your mind: coffee. Something new: travel
```

Followed by the normal capture/recall reply.

- Only sent once per week per bot session
- Not sent on other days of the week

---

## Phase 7 — `lc status` still works

```bash
lc status
```

**Expected:**
```
8 memories · Topics: coffee, hiking, dog · 7 days deep
```

---

## Phase 8 — lc topic depth after capture

```bash
lc "another coffee preference"
```

If this crosses the threshold (5, 10, or 20 atoms for "coffee"):

**Expected output:**
```
Saved. 1 new thing added to your memory.
You've saved 5 things about coffee. That's a topic you know well.
```

- Tracked in `~/.lattice/notified_depths.json` — shown once per subject, persists across `lc` runs

---

## Pass criteria

| Check | Pass if |
|---|---|
| `/api/usage/weekly` returns all fields | ✅ atoms, recalls, topics, new_topics, top_topic, streak |
| `/api/topic/depth` returns correct count | ✅ case-insensitive, excludes superseded |
| Topic depth card appears after 5+ atom subject recalled | ✅ card below answer with accent border |
| Correct depth message at 5/10/20 thresholds | ✅ matching label |
| Card shown only once (localStorage key) | ✅ gone after dismiss, never returns |
| Weekly report card on Monday with streak ≥7 | ✅ card in chat with this-week stats |
| Weekly report shown only once per week | ✅ localStorage key prevents repeat |
| Telegram topic depth after capture crosses threshold | ✅ message after save confirmation |
| Telegram weekly summary on first Monday interaction | ✅ prepended before capture/recall reply |
| `lc` topic depth after capture | ✅ message printed, tracked in notified_depths.json |
