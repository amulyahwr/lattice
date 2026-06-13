# Graph Schema Reference

## Current schema version: 1

The graph schema version is stored in `LATTICE_DIR/graph/manifest.json`. Lattice uses this to detect when a migration is needed on daemon startup.

## Manifest

```json
{
  "schema_version": 1,
  "atom_count": 147,
  "built_at": "2025-11-14T09:12:00Z"
}
```

## Node types

| Node type | ID format | Properties | Description |
|-----------|-----------|-----------|-------------|
| `atom` | `atom:<id>` | `id`, `kind`, `subject`, `quality_score`, `tier`, `is_superseded` | A memory atom |
| `source` | `source:<source_id>` | `source_id` | A capture channel or document |
| `segment` | `segment:<source_id>:<segment_id>` | `source_id`, `segment_id`, `role` | A sub-section of a source document |
| `subject` | `subject:<normalized>` | `label` | A normalized topic label |
| `episode` | `episode:<date>:<session_id>` | `date`, `session_id` | A capture session grouped by date + session |
| `insight` | `insight:<id>` | `id`, `content` | A serendipitous connection from the enrichment agent |

## Edge types

| Edge type | From → To | Properties | Description |
|-----------|----------|-----------|-------------|
| `atom_has_subject` | atom → subject | — | This atom is about this subject |
| `same_subject_as` | atom → atom | — | Two atoms share a normalized subject |
| `source_contains_segment` | source → segment | — | A document contains a section |
| `segment_contains_atom` | segment → atom | — | A section produced an atom |
| `supersedes` | atom → atom | `ts` | This atom replaced an older one |
| `same_hash` | atom → atom | — | Exact duplicate (normalized content hash) |
| `episode_contains_atom` | episode → atom | — | This atom belongs to this capture session |
| `supports_semantic` | atom → atom | `score` | Dense embedding similarity (cosine > threshold) |
| `leads_to_idea` | atom → insight | — | An atom contributed to a serendipitous insight |

## Sidecar files

```
LATTICE_DIR/graph/
├── nodes.jsonl     ← one node per line
├── edges.jsonl     ← one edge per line
└── manifest.json   ← schema_version, atom_count, built_at
```

Node line example:
```json
{"node_id": "atom:a1b2c3", "type": "atom", "id": "a1b2c3", "kind": "preference", "subject": "coffee preference", "quality_score": 1.3, "tier": "semantic", "is_superseded": false}
```

Edge line example:
```json
{"src": "atom:a1b2c3", "dst": "subject:coffee preference", "kind": "atom_has_subject"}
```

## Schema version history

| Version | Description | Migration |
|---------|-------------|-----------|
| `1` | Initial schema — atom, source, segment, subject nodes; 6 core edge types | — (baseline) |

> When new node or edge types are introduced (planned in STORY-049), the version increments and a migration entry is added here.

## Rebuilding the graph

If sidecars are corrupt or out of sync:

```bash
uv run lattice graph rebuild
```

This rebuilds `nodes.jsonl`, `edges.jsonl`, and `manifest.json` from all atoms in `LATTICE_DIR`. The daemon backs up the existing sidecars to `LATTICE_DIR/graph/backup/` before rebuilding.
