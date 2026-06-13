# Memory Tiers

Lattice organises atoms into three tiers that mirror how biological memory works. The tier affects how prominently an atom surfaces in recall.

## The three tiers

| Tier | Label | When assigned | Seed multiplier |
|------|-------|--------------|----------------|
| **Short-term** | `stm` | Atom is <48h old AND recall_count=0 | ×0.9 |
| **Episodic** | `episodic` | Default for atoms >48h old with low recall_count | ×1.0 |
| **Semantic** | `semantic` | Promoted by consolidation pipeline; high recall_count or explicit synthesis | ×1.1 |

## Short-term memory (STM)

Newly captured atoms start as STM. They're recent but unverified — Lattice hasn't seen any signal that they're useful yet.

STM atoms get a slight penalty (×0.9) in seed ranking. This means a freshly captured fact about "coffee preference" won't immediately drown out a well-established semantic atom on the same subject.

After 48 hours or the first recall, an atom graduates to `episodic`.

## Episodic memory

The default tier for most atoms. Episodic atoms are grouped into **episodes** — a capture session on a given date. The graph has `episode:<date>:<session_id>` nodes, and `episode_contains_atom` edges link each atom to its session.

This lets you answer temporal questions:
- "What did I capture last Tuesday?" → retrieve atoms from the `episode:2025-11-11` node
- "What was I thinking about during the project kickoff?" → retrieve atoms from the session where you captured project notes

## Semantic memory

Semantic atoms represent consolidated knowledge — facts that have proven useful enough to be promoted from episodic. They're produced by:

1. **Feedback** — atoms cited in multiple 👍-rated answers have higher `quality_score` and eventually `recall_count` thresholds
2. **Consolidation pipeline** — when a subject accumulates enough atoms (thresholds: 3/5/10/20), the pipeline creates a `kind=synthesis` atom that summarizes them, tier=semantic

Semantic atoms have a slight boost (×1.1) in seed ranking.

## The consolidation pipeline

When a subject reaches a threshold atom count, the consolidation pipeline runs:

1. **Extractive** (default, zero LLM): takes the top-3 most-recalled atoms on the subject and concatenates their content into a `kind=synthesis` atom. No cloud credits consumed.
2. **Generative** (opt-in, Ollama only): set `LATTICE_CONSOLIDATE_ENRICH=true` to have Ollama synthesize a richer summary. Never uses cloud LLM to avoid credit consumption.

The synthesis atom is linked to the source atoms via `supports_semantic` edges in the graph.

## Biological analogy

| Biological memory | Lattice equivalent |
|-------------------|-------------------|
| Working memory (seconds) | In-flight conversation context |
| Short-term memory (hours–days) | `tier=stm` atoms, fresh captures |
| Long-term episodic (specific events) | `tier=episodic` atoms, grouped by episode |
| Long-term semantic (distilled facts) | `tier=semantic` atoms, kind=synthesis |
| Insight / serendipity | `kind=insight` atoms, serendipity agent |

The consolidation pipeline is Lattice's equivalent of the brain's sharp-wave ripple process during sleep — turning episodic experiences into consolidated semantic knowledge.

## Episode nodes in the graph

Every capture session produces an episode node:

```
episode:2025-11-14:sess_abc123
    ├── episode_contains_atom → atom:a1b2c3  (coffee preference)
    ├── episode_contains_atom → atom:d4e5f6  (morning routine)
    └── episode_contains_atom → atom:g7h8i9  (sleep tracking)
```

This means a BFS query starting from any of these atoms can traverse to the others — even if they have completely different subjects. "What else did I capture the same day I noted my coffee preference?" is answerable via the graph.
