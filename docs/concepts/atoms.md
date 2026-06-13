# Atoms

An **atom** is the fundamental unit of memory in Lattice. It is a single, typed, timestamped fact — the smallest thing that can be independently useful.

## What an atom looks like on disk

Every atom is a plain `.md` file in `LATTICE_DIR` with YAML frontmatter:

```markdown
---
id: a1b2c3d4e5f6
kind: preference
subject: coffee preference
content: Prefers dark roast coffee, specifically Ethiopian single origin.
observed_at: 2025-11-14T09:12:00Z
source_id: telegram
session_id: sess_20251114_0912
quality_score: 1.3
recall_count: 4
last_recalled_at: 2025-12-01T14:30:00Z
tier: semantic
is_superseded: false
---
Prefers dark roast coffee, specifically Ethiopian single origin.
```

## Fields

### Identity

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | UUID-like hex identifier, unique across the store |
| `kind` | string | Atom type — see [Atom kinds](#atom-kinds) below |
| `subject` | string | Normalized topic label — the graph's primary join key |

### Provenance

| Field | Type | Description |
|-------|------|-------------|
| `observed_at` | ISO 8601 | When the fact was observed (not when it was ingested) |
| `source_id` | string | Channel that produced this atom: `telegram`, `lc-cli`, `mcp`, `web`, `inbox`, etc. |
| `session_id` | string | Session or document the atom came from |
| `segment_id` | string | Sub-segment within the source document |

### Content

| Field | Type | Description |
|-------|------|-------------|
| `content` | string | The fact itself, as a complete sentence |
| `valid_from` | ISO 8601 | When this fact became true (optional) |
| `valid_until` | ISO 8601 | When this fact stopped being true (optional) |

### Memory lifecycle

| Field | Type | Description |
|-------|------|-------------|
| `quality_score` | float | Relevance signal, updated by feedback loop. Range 0.1–2.0. Default 1.0. |
| `recall_count` | int | Times this atom appeared in a cited answer |
| `last_recalled_at` | ISO 8601 | Timestamp of most recent recall |
| `tier` | string | `stm` / `episodic` / `semantic` — see [Memory Tiers](memory-tiers.md) |
| `episode_id` | string | Episode group this atom belongs to (date + session) |

### Supersession

| Field | Type | Description |
|-------|------|-------------|
| `is_superseded` | bool | True if a newer atom for the same subject replaced this one |
| `superseded_by` | string | ID of the atom that superseded this one |
| `supersedes` | list[string] | IDs of atoms this atom replaced |

## Atom kinds

| Kind | What it represents |
|------|-------------------|
| `fact` | A factual statement about the world or a person |
| `preference` | A stated preference or taste |
| `goal` | Something the user wants to do or achieve |
| `decision` | A choice made, with context |
| `event` | A timestamped occurrence |
| `question` | An open question or uncertainty |
| `insight` | A connection noticed by the serendipity agent |
| `synthesis` | An LLM-generated summary of multiple atoms on the same subject |

## How atoms are created

You don't create atoms directly — Lattice extracts them. When you capture text, the ingest pipeline:

1. **Segments** the text by source type (chat turns, markdown headings, code blocks)
2. **Extracts** atoms via an LLM pass — one or many atoms per segment
3. **Detects supersession** — if an atom's subject already exists in the store, the old atom is linked as superseded
4. **Writes** the `.md` file and updates the graph

## Supersession: how Lattice updates facts

When you capture "I've switched to light roast coffee" after previously capturing "I prefer dark roast", Lattice:

1. Finds the existing `coffee preference` atom via the subjects index
2. Writes the new atom
3. Sets `is_superseded=true` on the old atom + links them bidirectionally
4. Old atom stays on disk — history is never deleted

The selection pipeline filters out superseded atoms, so synthesis never sees stale facts.

## Quality score

`quality_score` is a floating-point multiplier applied during BM25 seed ranking:

- Starts at `1.0` for every new atom
- `+0.1` when cited in a 👍-rated answer
- `-0.05` per recall cycle where the atom was retrieved but not cited (consistently ignored)
- `-0.2` when the user marks an answer as wrong and the atom was a source
- Floor: `0.1` — atoms never drop to zero
- Cap: `2.0`

High-quality atoms surface faster. Low-quality atoms fall to the back of the pack but remain retrievable.

## Human-editable

Atoms are plain markdown. You can open any `.md` file in `LATTICE_DIR` and edit fields directly. Lattice re-reads atoms from disk on access — edits take effect immediately. If you change a `subject` field, run `uv run lattice graph rebuild` to resync the graph.
