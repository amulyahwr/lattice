# Roadmap

For the full story backlog with acceptance criteria, see [STORIES.md](https://github.com/amulyahwr/lattice/blob/master/STORIES.md) in the repo.

## Current milestones

| Milestone | Status | Key stories |
|-----------|--------|-------------|
| M1 — Core ingest + file store | ✅ shipped | STORY-001–004 |
| M2 — BM25 selection | ✅ shipped | STORY-005 |
| M3 — Web UI | ✅ shipped | STORY-006–008 |
| M4 — MCP server | ✅ shipped | STORY-009 |
| M5 — Semantic search + spelling tolerance | ✅ shipped | STORY-010 |
| M6 — Telegram bot | ✅ shipped | STORY-018 |
| M7 — Multi-turn conversation | ✅ shipped | STORY-019–020 |
| M8 — Quality scoring feedback loop | planned | STORY-038 |
| M9 — Memory tiers + consolidation | planned | STORY-040–042 |
| M10 — Episode graph nodes | planned | STORY-040 |
| M11 — Serendipity agent | planned | STORY-043 |
| M12 — Graph schema versioning | planned | STORY-049 |

## Phase 2B (in progress)

Active distribution and UX work. See FEATURES.md for the full list.

## Phase 3 (planned)

- Episode nodes + consolidation pipeline
- Serendipity / ambient enrichment agent
- User taste profile
- Server-side session management + context management
- Telemetry opt-in + debug export

## Out of scope

- Hosted/cloud version — Lattice is local-first by design
- Atom deletion — quality scoring + archival achieves the retrieval quality goal without irreversible deletion
- LLM fine-tuning — RAG is strictly better for this use case; fine-tuning is static and has catastrophic forgetting risk
