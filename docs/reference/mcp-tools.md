# MCP Tools Reference

Lattice exposes five MCP tools to Claude Code. All tools are available when the MCP server is configured (see [MCP Setup](../getting-started/mcp-setup.md)).

---

## `lattice_ingest`

Save a fact or text chunk to memory.

**Use for:** a single fact, a decision, a preference, a short note.

```
lattice_ingest(
  text="decided to use PostgreSQL with UUID primary keys",
  source_id="claude-code",           # optional, defaults to "mcp"
  metadata={
    "source": "user",
    "observed_at": "2025-11-14T09:12:00Z"
  }
)
```

**Returns:** `{atoms_new, atoms_updated, duplicates_skipped, atom_ids}`

**When Claude Code calls this:** when you share a fact, decision, or preference during a conversation. Claude Code calls this immediately when you share something worth remembering.

---

## `lattice_capture`

Save a session summary. Wraps `lattice_ingest` with `source_id="claude-code"` and treats the input as a conversation chunk.

**Use for:** end-of-session summaries. Call this when the user says "save", "done", "wrap up", or "end session".

```
lattice_capture(
  text="user: ...\nassistant: ...",   # conversation chunk
  metadata={
    "source_id": "claude-code",
    "observed_at": "2025-11-14T10:30:00Z"
  }
)
```

**Returns:** same as `lattice_ingest`

---

## `lattice_select`

Find relevant atoms for a query. Returns raw atoms without synthesis — use when you want to inspect the evidence pack directly.

```
lattice_select(query="what did I decide about the database schema?")
```

**Returns:** list of atom dicts with `id`, `kind`, `subject`, `content`, `observed_at`, `source_id`, `quality_score`

**Use for:** when you want to ground an answer in retrieved atoms before composing a response yourself.

---

## `lattice_answer`

Find relevant atoms + synthesize a prose answer. One stop for recall questions.

```
lattice_answer(question="what coffee do I like?")
```

**Returns:** `{answer: str, atoms: list[dict], pii_protected: bool}`

**Use for:** when the user asks a recall question ("what did I decide about X?", "what do I prefer?", "remind me of Y"). Claude Code should call `lattice_answer` and ground the response in the returned atoms.

---

## `lattice_status`

Return atom count, streak, and today's activity.

```
lattice_status()
```

**Returns:**

```json
{
  "atom_count": 147,
  "streak_days": 12,
  "today": {
    "captures": 3,
    "recalls": 2
  },
  "pii_active": false
}
```

---

## Claude Code behavior guidelines

These are the rules Claude Code follows when Lattice MCP is configured:

1. **When the user shares a fact, preference, or decision** → call `lattice_ingest` immediately. Do not wait.
2. **When the user asks a recall question** → call `lattice_answer` first. Ground the response in returned atoms.
3. **When the user says "save", "done", "wrap up", or "end session"** → call `lattice_capture` with a summary of decisions and conclusions from the session.
4. **Single fact from the user** → set `metadata.source="user"`, `metadata.source_id="claude-code"`, `metadata.observed_at=<current ISO timestamp>`.
5. **Conversation chunk** → format as `"user: ...\nassistant: ..."` and omit `metadata.source` — the pipeline attributes per-turn automatically.
6. **Do not** save anything to `~/.claude/projects/.../memory/` — Lattice is the sole memory store.
