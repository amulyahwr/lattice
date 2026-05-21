# Architecture

lattice-mcp is a local-first MCP server that gives AI coding assistants persistent, structured memory. Raw text is decomposed into typed, timestamped **atoms** and stored as markdown files. A graph index connects atoms through provenance, subject, and supersession edges so retrieval can navigate context instead of scanning a flat folder.

---

## Pipeline

```
lattice_ingest(source, metadata)
        │
        ▼
   Segmentation          split by source type (markdown headings / chat turns / sliding window)
        │
        ▼
   LLM Extraction        one atom per fact: subject, kind, content, valid_from/until
        │
        ▼
   Dedup + Supersession  skip exact hash matches; LLM decides if new atom supersedes existing
        │
        ▼
   LatticeDB.write()     atomic write to LATTICE_DIR/<atom_id>.md
        │
        ▼
   LatticeGraph.add()    incremental update → graph/nodes.jsonl + edges.jsonl + manifest.json


lattice_select(query, as_of)
        │
        ▼
   BM25 search           top-20 non-superseded atoms scored on subject+content
        │
        ▼
   Graph BFS expansion   bounded BFS (depth=4, max=60 atoms) through committed
                         graph snapshot — traverses segment, source, subject,
                         supersedes, and same_hash edges in both directions
        │
        ▼
   Collapse + filter     drop superseded atoms; deduplicate by normalized hash;
                         apply as_of temporal filter
        │
        ▼
   Return atom dicts     with full provenance fields


lattice_answer(query, atom_ids?, as_of)
        │
        ├── atom_ids provided → read atoms directly from LatticeDB
        │
        └── no atom_ids → run lattice_select first
                │
                ▼
           LLM Synthesis    prose answer with temporal reasoning; explicit uncertainty
                            when selected atoms are weak or conflicting
```

---

## Module Map

| Module | Role |
|--------|------|
| `server.py` | MCP stdio entrypoint. Owns one shared `LatticeDB` instance per process. Routes `lattice_ingest`, `lattice_select`, `lattice_answer` tool calls. |
| `lattice/models.py` | `Atom` — Pydantic model with all provenance fields. Serialized to/from YAML frontmatter + markdown body via `python-frontmatter`. |
| `lattice/db.py` | `LatticeDB` — one `.md` file per atom in `LATTICE_DIR`. In-memory `_atom_cache`. `subjects.json` for O(1) subject lookup. Holds a `LatticeGraph` instance; updates it on every `write()` and `supersede()`. |
| `lattice/graph.py` | `LatticeGraph` — `networkx.MultiDiGraph` backed by committed sidecars. Incrementally updated; full rebuild triggered when manifest atom count diverges from disk. |
| `lattice/util.py` | Shared low-level helpers: `_normalized_subject()`, `_write_json_atomic()`. |
| `lattice/ingest.py` | Segments source text → LLM extracts atoms → dedup + supersession check → write to DB. |
| `lattice/selection.py` | BM25 pre-filter → graph BFS expansion via `LatticeGraph.bfs_expand()` → collapse superseded/duplicate groups. Falls back to `evidence_pack()` if graph is empty. Exports `_atom_to_dict()` for consistent atom serialization. |
| `lattice/synthesis.py` | Takes atom dicts + query → LLM produces prose answer. |
| `lattice/llm.py` | Thin litellm wrapper. Single `complete(messages) → str` interface. Reads `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` from env. Raises `EnvironmentError` eagerly if API key missing. |

---

## Atom Data Model

Every atom is a `.md` file with YAML frontmatter:

```
atom_id              UUID (stable, used in supersession links and lattice_answer calls)
kind                 free-form: fact | event | decision | preference | belief | …
source               free-form: user | document | chat | code | …
subject              canonical noun phrase — normalized for subject index and graph edges
content              self-contained statement of the fact
valid_from/until     optional date bounds; as_of queries exclude atoms outside window
is_superseded        true when a newer atom has replaced this one
supersedes           atom_id of the older version this atom replaced
superseded_by        atom_id of the newer version that replaced this atom
ingested_at          when the atom was written
observed_at          when the fact was observed in the source
source_id            groups all atoms from one ingest call / document
session_id           groups atoms from one conversation turn window
segment_id           chunk within a segmented source (s0, s1, …)
source_type          markdown | chat | code | plain
source_span          {start, end} byte offsets into original source
content_hash         SHA256 of exact content (exact dedup)
normalized_content_hash  SHA256 of lowercased word-tokenized content (fuzzy dedup)
metadata             passthrough dict from lattice_ingest caller
```

---

## Graph Index

After every atom write, `LatticeGraph` upserts nodes and edges into a `networkx.MultiDiGraph` and writes committed sidecars to `LATTICE_DIR/graph/`.

**Node types:**

| ID pattern | Represents |
|-----------|-----------|
| `atom:<atom_id>` | One per atom (including superseded) |
| `source:<source_id>` | One per unique source document / ingest batch |
| `segment:<container_id>:<segment_id>` | One per chunk; container = source_id or session_id |
| `subject:<normalized>` | One per unique normalized subject string |

**Edge types:**

| Type | Direction | Meaning |
|------|-----------|---------|
| `atom_has_subject` | atom → subject | Always present |
| `same_subject_as` | atom ↔ atom | Bidirectional; same normalized subject |
| `source_contains_segment` | source → segment | When atom has source_id + segment_id |
| `segment_contains_atom` | segment → atom | When atom has segment_id |
| `supersedes` | new atom → old atom | Written by `db.supersede()` |
| `same_hash` | atom → atom | Same `normalized_content_hash` |

**Sidecar files:**

```
LATTICE_DIR/
  graph/
    nodes.jsonl       one JSON line per node {id, type, …attrs}
    edges.jsonl       one JSON line per edge {src, dst, type, key}
    manifest.json     {version, atom_count, edge_count, built_at}
```

`preload()` loads sidecars when `manifest.atom_count` matches disk atom count; otherwise rebuilds from scratch. All writes are atomic (tempfile + rename).

---

## Key Design Invariants

- **Local-only.** No hosted service, no daemon, no external DB. Everything in `LATTICE_DIR`.
- **Human-readable atoms.** `.md` files can be hand-edited, deleted, or committed to git without breaking the server.
- **Committed snapshots.** Selection reads stable graph/BM25 snapshots; it never waits for active ingest.
- **Superseded atoms stay on disk** with `is_superseded=true` and bidirectional links. History is preserved, not deleted.
- **Expensive enrichment is optional.** Embeddings, semantic relation enrichment, and hub labeling are roadmap items that must remain off by default for Ollama users.
- **LLM calls are mockable at the module level.** Tests patch `lattice.ingest.complete`, `lattice.selection.complete`, `lattice.synthesis.complete` — not `lattice.llm.complete`.

---

## Roadmap Direction

Current state (P6 done): BM25 seeds → graph BFS expansion → collapse superseded/duplicates → LLM answer.

Next: optional semantic relation enrichment (P8), topic hubs (P9), embeddings (P11). Full roadmap in `lattice/eval/PRIORITIES.md`.
