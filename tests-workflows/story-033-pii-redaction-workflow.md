# STORY-033 Test Workflow — PII Round-Trip Redaction

Verifies that PII (emails, phone numbers, and optionally person/org names via NER) is redacted
before text reaches a cloud LLM, and restored in atoms on disk and in synthesis output.

**Active when:** `LLM_PROVIDER != ollama` AND `LATTICE_PII_SCRUB` is not `"0"` or `"false"` (default: on).
**Ollama users:** feature is a no-op. No configuration needed.

---

## Pre-flight

```bash
# Confirm daemon is running with a cloud provider
uv run lattice-daemon status

# Check env vars
echo $LLM_PROVIDER      # must be "openai", "anthropic", or OpenRouter — NOT "ollama"
echo $LATTICE_PII_SCRUB # should be unset (defaults to true) or "true"
echo $LATTICE_NER_MODEL # optional: local Ollama model for NER (e.g. qwen3:0.6b)
```

If `LLM_PROVIDER=ollama`, PII scrubbing is intentionally skipped — data never leaves the machine.

---

## Phase 1 — Regex path (emails + phones, no NER model needed)

This is the default path when `LATTICE_NER_MODEL` is not set.

### 1a. Ingest text containing PII

```bash
lc "Meeting notes: contact sarah.chen@acme.com or call her at 415-555-0192 to confirm the workshop."
```

**Expected:**
- Daemon receives: `EMAIL_0` and `PHONE_0` in place of real values
- Atoms on disk: real email and phone restored (check `~/.lattice/*.md` for the new atom)
- `content` in the atom file contains `sarah.chen@acme.com` and `415-555-0192`

```bash
# Verify the atom on disk has real values
grep -r "sarah.chen\|415-555" ~/.lattice/*.md
```

### 1b. Ingest via Web UI

1. Open `http://localhost:7337`
2. Use the file upload or type a note with an email address
3. Confirm atoms in Recent Memories show real values

### 1c. Ingest via Telegram

Send a message containing an email to the bot. Reply should confirm save; the stored atom should have the real email.

---

## Phase 2 — Synthesis path (PII protected badge)

Verify that the synthesis response has real names, not `EMAIL_0` or `PHONE_0` tags.

### 2a. Recall the ingested PII atom

In the web UI, ask:

```
What is Sarah's email?
```

**Expected:**
- Answer contains `sarah.chen@acme.com` (restored, not a tag)
- A small `🔒 PII protected` badge appears above the answer

### 2b. Verify no tags leak through

Check the answer text. If you see `EMAIL_0`, `PHONE_0`, or `PER_0` in the rendered answer, the restore step failed — file a bug.

---

## Phase 3 — NER path (person + org names, requires LATTICE_NER_MODEL)

Skip this phase if you don't have a local Ollama model available.

### 3a. Set NER model

```bash
export LATTICE_NER_MODEL=qwen3:0.6b   # or any small model you have pulled
# Restart daemon to pick up env change
uv run lattice-daemon stop && uv run lattice-daemon start
```

### 3b. Ingest text with named persons and orgs

```bash
lc "James Roth from Vertex Capital called. He's joining as CTO of NovaTech starting March. His email is james.roth@novatech.io."
```

**Expected on disk:**
- Atom content contains `James Roth`, `Vertex Capital`, `NovaTech`, `james.roth@novatech.io` (all restored)
- Cloud LLM only saw: `PER_0`, `ORG_0`, `ORG_1`, `EMAIL_0`

```bash
grep -r "James Roth\|Vertex Capital\|NovaTech" ~/.lattice/*.md
```

### 3c. Recall and verify

In web UI:

```
What do I know about James Roth?
```

**Expected:**
- Real name and org in the answer
- `🔒 PII protected` badge visible
- No `PER_0` or `ORG_0` tags in the rendered text

---

## Phase 4 — Ollama no-op confirmation

Verify redaction is fully skipped on the Ollama path.

```bash
export LLM_PROVIDER=ollama
export LLM_MODEL=qwen3:4b
uv run lattice-daemon stop && uv run lattice-daemon start

lc "Reminder: contact mike@example.com about the project."
```

**Expected:**
- Ingest works normally, no redaction overhead
- No `🔒 PII protected` badge in web UI recall
- `privacy.is_active()` returns False (Ollama path)

---

## Phase 5 — Explicit disable

Verify `LATTICE_PII_SCRUB=false` turns off redaction even on cloud providers.

```bash
export LLM_PROVIDER=openai
export LATTICE_PII_SCRUB=false
uv run lattice-daemon stop && uv run lattice-daemon start

lc "Contact alice@startup.com for the demo."
```

**Expected:**
- Ingest succeeds, no tags substituted
- No badge in recall

---

## Phase 6 — Multi-segment document (batch entity_map consistency)

Verify that a long document with the same person name across multiple segments produces consistent tags (not `PER_0` in segment 1 and `PER_1` in segment 2 for the same name).

Drop a multi-page document mentioning the same person on different pages:

```bash
cp ~/Downloads/report.pdf ~/.lattice/inbox/
```

**Expected:**
- All atoms from this document refer to the same person with consistent real name after restore
- No orphaned `PER_N` tags in any atom content

---

## Acceptance checklist

| Check | Expected |
|-------|----------|
| Email in ingested atom | Real email on disk |
| Phone in ingested atom | Real phone on disk |
| Person name (NER, if set) | Real name on disk |
| Synthesis answer | Real values, not tags |
| Web UI badge | `🔒 PII protected` visible when active |
| Ollama path | No badge, no redaction overhead |
| `LATTICE_PII_SCRUB=false` | No redaction, no badge |
| Multi-segment doc | Consistent entity numbering across all segments |

---

## Troubleshooting

**`PER_0` / `EMAIL_0` visible in synthesis answer:**
Tags not restored. Check that `entity_map` is non-empty and `EntityRedactor().restore()` is being called after the LLM response. Verify `LATTICE_PII_SCRUB` is not `"0"` and `LLM_PROVIDER` is not `"ollama"`.

**NER model not running:**
`LATTICE_NER_MODEL` requires a locally pulled Ollama model. Run `ollama list` to confirm the model is available. If missing, run `ollama pull qwen3:0.6b`. NER failure is silent — falls back to regex-only, not a crash.

**No badge in web UI despite cloud provider:**
The badge only appears when `entity_map` is non-empty (i.e., PII was actually found in the atom content). If atoms contain no emails, phones, or names, no redaction runs and no badge shows. Try ingesting content with a clear email address.

**Date values redacted:**
Dates must never be redacted (breaks temporal reasoning). If you see `DATE_0` in atom content, file a bug — this should not happen with the current regex/NER configuration.
