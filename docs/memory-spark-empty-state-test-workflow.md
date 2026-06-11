# STORY-029 Test Workflow — Memory Sparks

Verifies ghost queries, spark cards, and topic suggestions across Web UI, Telegram, and `lc status`.

---

## Pre-flight

```bash
lattice-start
open http://localhost:7337
```

Make sure you have at least a few atoms stored. If not, ingest a couple first:

```bash
lc "I prefer dark roast coffee"
lc "decided to use Postgres for the new project"
lc "hiking in Patagonia is on my bucket list"
```

Wait a few seconds for the daemon to process, then reload the browser.

---

## Phase 1 — Web UI: Spark cards in empty state

Open `http://localhost:7337` with no conversation active.

**Expected:**
- Below the cube logo, 3 spark cards appear — one per recent atom
- Each card shows a kind icon, a generated question, and a time label ("from yesterday", "3 days ago")
- Questions follow the pattern:
  - `"What do I prefer about coffee?"` (kind=preference)
  - `"What did I decide about Postgres?"` (kind=decision)
  - `"Tell me about hiking"` (kind=fact or other)

**Verify:**
- Cards are visible in the empty state area
- Hovering a card causes a subtle scale animation (no jarring jump)
- Clicking a card fills the input and submits immediately → answer streams in

---

## Phase 2 — Web UI: Ghost queries in input placeholder

With no conversation active, look at the question input.

**Expected:**
- Placeholder text cycles every 3 seconds through example questions built from your stored atoms
- Examples: `"What do I prefer about coffee?"`, `"What did I decide about Postgres?"`
- Cycling is smooth (no hard flash)
- Falls back to `"Ask your memory anything…"` if no atoms exist

**Verify:**
- Watch the placeholder for ~10 seconds — it should cycle through 2–4 queries
- Clicking in the input does not auto-fill the placeholder text (the input stays blank for you to type)

---

## Phase 3 — Web UI: Spark cards disappear on first question

Type a question and press Enter (or click a spark card to submit).

**Expected:**
- Empty state (including spark cards) disappears
- Ghost query cycling stops
- Input placeholder becomes static `"Ask anything…"`
- Normal conversation UI takes over

---

## Phase 4 — Web UI: True empty state (no atoms)

Test with a fresh Lattice directory or temporarily rename `~/.lattice`:

```bash
mv ~/.lattice ~/.lattice.bak
mkdir ~/.lattice
lattice-start   # restart daemon pointing to empty dir
```

Open `http://localhost:7337`.

**Expected:**
- No spark cards shown
- No ghost queries — placeholder is static `"Ask your memory anything…"`
- A message appears: *"Your memory starts here. Save something worth keeping, then come back and ask about it."*

Restore afterward:

```bash
lattice-stop
rm -rf ~/.lattice
mv ~/.lattice.bak ~/.lattice
lattice-start
```

---

## Phase 5 — Telegram `/start`

Send `/start` to your Telegram bot.

**With atoms stored — expected reply includes:**
```
You could ask:
· What do I prefer about coffee?
· What did I decide about Postgres?
· Tell me about hiking

Or just send me a thought and I'll save it.
```

**With no atoms stored — expected:**
```
Hey, good to have you here.

Send me anything worth keeping — a decision you made, something you learned,
a preference you want to remember. I'll hold onto it and surface it when you need it.

What's on your mind?
```

No command listing — when nothing is stored, there's nothing to recall or count. Focus is entirely on the first capture.

---

## Phase 6 — `lc status`

```bash
lc status
```

**Expected output (with atoms):**
```
12 memories · Topics: coffee, Postgres, hiking, travel, books
```

- Memory count is accurate (non-superseded only)
- Up to 5 topics shown in ingestion order
- Topics are real subject strings — no IDs or hashes

**With no atoms:**
```
0 memories stored
```

No `Topics:` line when nothing is stored.

---

## Pass criteria

| Check | Pass if |
|---|---|
| Spark cards show in empty state | ✅ 3 cards from recent atom subjects |
| Card questions match atom kind | ✅ preference/decision/other → correct template |
| Clicking a card submits the question | ✅ answer streams in immediately |
| Ghost query cycles every ~3s | ✅ placeholder rotates through atom-based questions |
| Cards disappear once conversation starts | ✅ empty state removed on first turn |
| True empty state shows message, not cards | ✅ no cards, helpful text instead |
| Telegram `/start` with atoms shows suggestions | ✅ up to 3 suggestions |
| Telegram `/start` with no atoms shows empty message | ✅ encouraging fallback |
| `lc status` shows topic list | ✅ `· Topics: subject1, subject2, …` |
| `lc status` with no atoms omits topics line | ✅ only count shown |
| Superseded atoms excluded from topic list | ✅ only active atoms listed |
