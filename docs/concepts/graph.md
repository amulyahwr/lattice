# The Graph

Lattice maintains a heterogeneous graph alongside the atom store. The graph is what turns a flat list of facts into a connected memory — it's how Lattice knows that your "coffee preference" atom is related to your "morning routine" atom and your "sleep tracking" atom.

## What it is

A `networkx MultiDiGraph` where every atom, source, segment, and subject is a node, and relationships between them are typed directed edges.

The graph is stored as committed sidecars in `LATTICE_DIR/graph/`:

```
~/.lattice/graph/
├── nodes.jsonl      ← one JSON object per line, one node per object
├── edges.jsonl      ← one JSON object per line, one edge per object
└── manifest.json    ← schema_version, atom_count, built_at
```

On daemon startup, if `manifest.atom_count` matches the live atom count, the graph is loaded from sidecars (fast). Otherwise it's rebuilt from atoms (slower but always correct).

## Node types

| Node type | Example ID | What it represents |
|-----------|-----------|-------------------|
| `atom` | `atom:a1b2c3` | A memory atom |
| `source` | `source:telegram` | The channel that produced atoms |
| `segment` | `segment:doc1:seg3` | A sub-section of a source document |
| `subject` | `subject:coffee preference` | A normalized topic label |
| `episode` | `episode:2025-11-14:sess_abc` | A capture session grouped by date + session |
| `insight` | `insight:i9k2m1` | A serendipitous connection noticed by the enrichment agent |

## Edge types

| Edge type | From → To | What it represents |
|-----------|----------|-------------------|
| `atom_has_subject` | atom → subject | This atom is about this subject |
| `same_subject_as` | atom → atom | Two atoms share a subject |
| `source_contains_segment` | source → segment | A document contains a section |
| `segment_contains_atom` | segment → atom | A section produced an atom |
| `supersedes` | atom → atom | This atom replaced an older one |
| `same_hash` | atom → atom | Exact duplicate detection |
| `episode_contains_atom` | episode → atom | This atom belongs to this capture session |
| `supports_semantic` | atom → atom | Dense embedding similarity (cosine > threshold) |
| `leads_to_idea` | atom → insight | An atom contributed to a serendipitous insight |

## How the graph is used in selection

The selection pipeline uses graph BFS to expand the evidence pack beyond what BM25 finds:

```
BM25 seeds (top-k atoms by text score)
    ↓
Graph BFS expansion:
  - same_subject_as → related atoms on the same topic
  - supersedes → follow supersession chains (for temporal queries)
  - segment_contains_atom → other atoms from the same source document
  - episode_contains_atom → other atoms from the same capture session
    ↓
Merged, deduplicated, re-ranked by decay score
    ↓
Superseded atoms filtered out
    ↓
Atom pack → synthesis
```

This is why Lattice can answer "what did I think about X last month?" — the graph connects atoms captured in the same session or from the same document, even if the text of those atoms doesn't keyword-match the query.

## Subject nodes: the primary join key

Every atom has a `subject` field. The subject is normalized (lowercased, punctuation stripped) and used as a join key. When two atoms have the same subject, they are linked by `same_subject_as` edges.

The `subjects.json` file in `LATTICE_DIR` is an index of `subject → [atom_id, ...]` for O(1) supersession lookups.

## Inspecting the graph

You can read the sidecars directly:

```bash
# count nodes by type
cat ~/.lattice/graph/nodes.jsonl | python3 -c "
import sys, json, collections
c = collections.Counter(json.loads(l)['type'] for l in sys.stdin)
print(c)
"

# count edges by type
cat ~/.lattice/graph/edges.jsonl | python3 -c "
import sys, json, collections
c = collections.Counter(json.loads(l)['kind'] for l in sys.stdin)
print(c)
"
```

## Schema versioning

`manifest.json` includes a `schema_version` field. When Lattice introduces new node or edge types (e.g., `episode` nodes in STORY-040), the migration runner in `lattice/migrations/` handles the upgrade transparently on daemon startup. See [Graph Schema Reference](../reference/graph-schema.md) for version history.

## Rebuilding the graph

If the graph gets out of sync (e.g., after manual edits to atom files):

```bash
uv run lattice graph rebuild
```

This scans all atoms in `LATTICE_DIR` and rebuilds `nodes.jsonl`, `edges.jsonl`, and `manifest.json` from scratch.
