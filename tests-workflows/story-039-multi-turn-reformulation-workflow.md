# STORY-039 — Multi-turn Query Reformulation Test Workflow

Verifies follow-up detection, query reformulation, `chat.jsonl` writing, conversation history
restore on page reload, inactivity reset, Telegram history passing, and `lc` followup tip.

---

## Pre-flight

```bash
uv run lattice-daemon status
open http://localhost:7337
```

Confirm daemon running (`{"ok": true}`). Confirm atoms are present (`lc status` > 0).

---

## Phase 1 — Unit tests (automated)

```bash
uv run pytest tests/test_story_039.py -v
```

Expected: **37 passed**. Covers `is_followup()` true/false cases, `reformulate()` LLM call,
fallbacks (empty, identical, too-long, exception), model resolution chain, config env vars.

---

## Phase 2 — Seed test atoms

Drop a short conversation so there are atoms to recall:

```bash
cat > ~/.lattice/inbox/s039-test.txt << 'EOF'
user: I decided to use Postgres over SQLite for the new service because of better concurrency and WAL support. Made this call on June 1st.
assistant: Good choice. Postgres handles concurrent writes much better than SQLite. WAL mode in SQLite helps but it's still single-writer. For a service expecting multiple connections, Postgres is the right call.
user: I also prefer using connection pooling via PgBouncer rather than application-level pooling.
assistant: PgBouncer in transaction mode is a solid default. It keeps connection counts low and works well with most ORMs.
EOF
```

Wait ~5 seconds, confirm processed:

```bash
ls ~/.lattice/processed/ | grep s039-test
lc status
```

Atom count should increase by 3–5.

---

## Phase 3 — Non-followup query (zero reformulation latency) [MANUAL]

In the web UI (`http://localhost:7337`), ask a self-contained question:

```
What did I decide about the database for the new service?
```

Expected:
- Answer references the Postgres decision, cites sources
- No added latency — reformulation does not trigger for self-contained queries

Inspect `chat.jsonl` to confirm the turn was recorded:

```bash
tail -1 ~/.lattice/chat.jsonl | python3 -m json.tool
```

Expected record:
```json
{
  "ts": "2026-...",
  "session_id": "<uuid>",
  "question": "What did I decide about the database for the new service?",
  "answer": "...",
  "atom_ids": ["<uuid-1>", ...],
  "channel": "web"
}
```

Note: `reformulated_query` field should be **absent** (no reformulation triggered).

---

## Phase 4 — Follow-up query triggers reformulation [MANUAL]

Immediately after Phase 3, without reloading the page, ask:

```
when was that?
```

Expected:
- `is_followup("when was that?")` → `True` (short + anaphoric)
- LLM reformulates to something like: `"When did I decide to use Postgres over SQLite?"`
- Answer returns the date (June 1st) from the stored atom
- User sees a normal answer — no reformulation indicator shown

Inspect `chat.jsonl`:

```bash
tail -1 ~/.lattice/chat.jsonl | python3 -m json.tool
```

Expected: `reformulated_query` field **present** with the expanded question:
```json
{
  "question": "when was that?",
  "reformulated_query": "When did I decide to use Postgres over SQLite for the new service?",
  "answer": "...",
  ...
}
```

---

## Phase 5 — Additional follow-up forms [MANUAL]

Test other phrase-list fast-paths in the same session:

| Query | Expected behaviour |
|---|---|
| `why?` | Reformulates to "Why did I choose Postgres over SQLite?" |
| `what else?` | Reformulates using last Q&A context |
| `tell me more` | Reformulates and expands on last answer |
| `What do I know about PgBouncer?` | **No reformulation** — proper noun, self-contained |

For each, check `chat.jsonl` tail to confirm `reformulated_query` present/absent as expected.

---

## Phase 6 — chat.jsonl verification (automated)

```bash
# Confirm file exists and has records
wc -l ~/.lattice/chat.jsonl

# Check all records are valid JSON
python3 -c "
import json
path = __import__('pathlib').Path.home() / '.lattice/chat.jsonl'
records = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
print(f'{len(records)} records')
required = {'ts', 'question', 'answer', 'atom_ids', 'channel'}
for i, r in enumerate(records):
    missing = required - r.keys()
    if missing: print(f'Record {i} missing: {missing}')
print('All fields present' if all((required - r.keys()) == set() for r in records) else 'Some fields missing')
"
```

Expected: all records valid, all required fields present.

---

## Phase 7 — Conversation history survives page reload [MANUAL]

1. Ask: `What did I decide about the database?` — get answer
2. Ask: `when was that?` — confirm reformulation works (from Phase 4)
3. **Reload the page** (`Cmd+R`)
4. Ask: `what were the reasons again?`

Expected: reformulation triggers and resolves to the Postgres decision context — history
was restored from `GET /api/chat/recent?session_id=<id>` on page load.

If history is NOT restored: the question returns a generic or unrelated answer.

---

## Phase 8 — LATTICE_REFORMULATION=0 disables reformulation (automated)

```bash
LATTICE_REFORMULATION=0 python3 -c "
from lattice.config import Config
cfg = Config.from_env()
print('reformulation_enabled:', cfg.reformulation_enabled)
assert cfg.reformulation_enabled is False, 'Should be disabled'
print('PASS')
"
```

Also verify `_apply_reformulation` short-circuits:

```bash
python3 -c "
import os; os.environ['LATTICE_REFORMULATION'] = '0'
from lattice.config import Config
from lattice.web.app import _apply_reformulation

class FakeReq:
    question = 'when was that?'
    conversation_history = [{'question': 'Q', 'answer': 'A'}]
    session_id = None

cfg = Config.from_env()
result = _apply_reformulation(FakeReq(), cfg)
assert result == 'when was that?', f'Expected original, got: {result}'
print('PASS — reformulation correctly disabled')
"
```

---

## Phase 9 — LATTICE_CONVERSATION_TURNS env var (automated)

```bash
python3 -c "
import os; os.environ['LATTICE_CONVERSATION_TURNS'] = '4'
from lattice.config import Config
cfg = Config.from_env()
assert cfg.conversation_turns == 4
print('PASS — conversation_turns=4')
"
```

---

## Phase 10 — REFORMULATION_MODEL resolution chain (automated)

```bash
python3 -c "
from lattice.config import Config
from lattice.llm import resolve_model

# Case 1: REFORMULATION_MODEL set explicitly
cfg = Config(lattice_dir='/tmp', llm_provider='openai', llm_model='gpt-4o',
             ingest_model='haiku', reformulation_model='gpt-4o-mini')
assert resolve_model(cfg, cfg.reformulation_model or cfg.ingest_model) == 'gpt-4o-mini'
print('PASS — explicit REFORMULATION_MODEL used')

# Case 2: falls back to INGEST_MODEL
cfg2 = Config(lattice_dir='/tmp', llm_provider='openai', llm_model='gpt-4o',
              ingest_model='gpt-4o-mini', reformulation_model=None)
assert resolve_model(cfg2, cfg2.reformulation_model or cfg2.ingest_model) == 'gpt-4o-mini'
print('PASS — falls back to INGEST_MODEL')

# Case 3: falls back to LLM_MODEL
cfg3 = Config(lattice_dir='/tmp', llm_provider='openai', llm_model='gpt-4o',
              ingest_model=None, reformulation_model=None)
assert resolve_model(cfg3, cfg3.reformulation_model or cfg3.ingest_model) == 'gpt-4o'
print('PASS — falls back to LLM_MODEL')
"
```

---

## Phase 11 — lc followup tip [MANUAL]

```bash
lc "when was that?"
```

Expected output (tip printed, then capture proceeds normally):
```
Tip: lc is single-shot — rephrase as a complete question for best results.
Saved. N new ideas added to your memory.
```

```bash
lc "What did I decide about the Postgres migration on June 1st?"
```

Expected: **no tip** (self-contained query, proper noun present).

---

## Phase 12 — Telegram follow-up [MANUAL]

In Telegram, send to your Lattice bot:

1. `/ask what did I decide about the database?`
   - Expected: answer about Postgres decision

2. `/ask when was that?`
   - Expected: reformulation fires, answer returns June 1st date

3. Check `chat.jsonl` for a `"channel": "telegram"` record with `reformulated_query` present.

---

## Pass criteria

| Check | How to verify | Pass if |
|---|---|---|
| Unit tests 37/37 | Phase 1 | All green |
| Non-followup: no `reformulated_query` in chat.jsonl | Phase 3 | Field absent |
| Followup: `reformulated_query` present in chat.jsonl | Phase 4 | Field present, expanded question |
| Phrase fast-paths trigger reformulation | Phase 5 | `why?`, `tell me more`, etc. reformulate |
| Proper noun query skips reformulation | Phase 5 | `What do I know about PgBouncer?` → no field |
| chat.jsonl all records valid JSON | Phase 6 | All fields present |
| History restores on page reload | Phase 7 | Followup resolves after reload |
| `LATTICE_REFORMULATION=0` disables | Phase 8 | Returns original query |
| `LATTICE_CONVERSATION_TURNS` env var | Phase 9 | Config field correct |
| Model resolution chain | Phase 10 | Correct model at each fallback level |
| `lc` tip on followup query | Phase 11 | Tip printed; not printed for self-contained |
| Telegram followup works | Phase 12 | `chat.jsonl` has telegram record with reformulated_query |
