# M4 — Source Feedback Test Workflow

Verifies per-source dismiss, `you said` / `assistant said` attribution tags, and `dismissed_atom_ids` + `citation_map` captured in `feedback.jsonl`.

---

## Pre-flight

```bash
uv run lattice-daemon status
open http://localhost:7337
```

Confirm daemon is running (status returns `{"ok": true}`).

---

## Phase 1 — Seed test atoms with user + assistant roles

Drop a short conversation into the inbox so atoms carry both `source=user` and `source=assistant`:

```bash
cat > ~/.lattice/inbox/m4-test-convo.txt << 'EOF'
user: I've been training for a half marathon. Running 4 days a week now.
assistant: That's a solid base. For a half marathon you'll want to add one long run per week, building to 10–12 miles before race day. Make sure to include at least one rest day between hard efforts.
user: I also want to improve my 5K time to under 22 minutes.
assistant: To break 22 minutes you need to be running roughly 7:04 pace. Add one interval session per week — 6×800m at your goal pace with 90 seconds recovery works well at your current training volume.
EOF
```

Wait ~5 seconds for the daemon to process. Confirm the file moved:

```bash
ls ~/.lattice/processed/ | grep m4-test-convo
```

Check atoms were created:

```bash
lc status
```

Count should increase by at least 3–4 atoms.

---

## Phase 2 — Trigger a recall and inspect source cards

In the web UI (`http://localhost:7337`), ask:

```
what are my running goals?
```

Expected: answer streams in, Sources section expands below.

**Check: attribution tags**

Open the Sources section. Each card from the ingested conversation should show either:
- `you said` — for atoms extracted from the user turns
- `assistant said` — for atoms extracted from the assistant turns

Cards from other capture channels (`lc`, web, browser extension) show the channel label as before (no attribution tag).

**Check: dismiss button**

Hover over any source card. A small `✕` button should appear on the right side of the card.

---

## Phase 3 — Dismiss a source and verify visual state

Click `✕` on one source card.

Expected:
- Card dims to ~35% opacity
- Content preview shows strikethrough text
- `✕` button disappears (disabled)
- Card stays in place — inline citation `[N]` in the answer text still resolves

Optionally dismiss a second card. Both should dim independently.

---

## Phase 4 — Submit feedback and inspect feedback.jsonl

Click 👍 **Yes** (or 👎 → pick a reason chip).

Then inspect the last record in `feedback.jsonl`:

```bash
tail -1 ~/.lattice/feedback.jsonl | python3 -m json.tool
```

Expected record shape:

```json
{
  "ts": "2026-...",
  "question": "what are my running goals?",
  "answer": "...",
  "rating": "up",
  "reason": null,
  "atom_ids": ["<uuid-1>", "<uuid-2>", "..."],
  "dismissed_atom_ids": ["<uuid-of-dismissed-card>"],
  "citation_map": {
    "<uuid-1>": "1",
    "<uuid-2>": "2",
    "<uuid-3>": "3"
  }
}
```

**Verify:**
- `dismissed_atom_ids` contains exactly the UUIDs of the cards you dismissed (one per ✕ click)
- `citation_map` maps citation numbers (`"1"`, `"2"`, …) to atom UUIDs
- `atom_ids` is the full set of cited atoms (superset of `dismissed_atom_ids`)

---

## Phase 5 — No-feedback path (dismiss only, no rating submitted)

Ask another question, dismiss a source card, then **do not submit** 👍/👎.

Start a new question. Confirm no extra feedback record was written:

```bash
wc -l ~/.lattice/feedback.jsonl
```

Line count should be the same as after Phase 4. Dismissals without a rating are intentionally not persisted — expected behaviour.

---

## Phase 6 — Non-chat atoms show no attribution

Capture something via `lc`:

```bash
lc "I prefer morning workouts before 8am"
```

Ask a question that retrieves this atom:

```
when do I prefer to work out?
```

In the Sources section, the atom captured via `lc` should show `claude-code` (or whatever `source_id` was set) as the channel label — **not** `you said` or `assistant said`. Attribution only appears for atoms with `source=user` or `source=assistant` from parsed conversations.

---

## Pass criteria

| Check | Pass if |
|---|---|
| Conversation atoms show `you said` / `assistant said` | ✅ tag visible on source cards from parsed chat |
| `lc` / web atoms show channel label (no attribution) | ✅ `you said` absent; channel label shown instead |
| Hover reveals `✕` dismiss button | ✅ button appears on hover, hidden otherwise |
| Click `✕` → card dims, strikethrough, button gone | ✅ `.dismissed` class applied, card stays in DOM |
| Inline citation `[N]` still resolves after dismiss | ✅ clicking `[N]` in answer still highlights dimmed card |
| Submit 👍/👎 → `dismissed_atom_ids` in feedback.jsonl | ✅ field present with correct UUIDs |
| `citation_map` maps numbers to atom UUIDs | ✅ `{"1": "<uuid>", ...}` in record |
| Dismiss without submitting feedback → no new record | ✅ `wc -l feedback.jsonl` unchanged |
| Dismissing 2 cards → both UUIDs in one record | ✅ `dismissed_atom_ids` has 2 entries |
