# What is Lattice?

## The problem

Your life generates more than you can hold. Decisions, reminders, half-formed ideas, things you learned last Tuesday — most of it disappears. Apps for notes, apps for tasks, apps for bookmarks — none of them talk to each other, and none of them answer questions about what's in them.

The right pieces now exist: local LLMs that can extract structure from free text, embed-and-search that can find semantically similar ideas, graph databases that can trace connections. But every tool built on them stores your memories as flat blobs of text, with no structure and no connections. Worse, they live on someone else's server.

## What Lattice is

Lattice turns every thought you capture into a small, typed, timestamped **atom** — a plain `.md` file with YAML frontmatter:

```markdown
---
id: a1b2c3
kind: preference
subject: programming language preference
observed_at: 2025-11-14T09:12:00Z
source_id: telegram
quality_score: 1.2
tier: semantic
---
Prefers Python over Go for scripting. Finds Go's verbosity frustrating for
one-off tooling.
```

Atoms are:

- **Human-readable** — open any atom in a text editor
- **Git-trackable** — your memory store is just a folder of markdown files
- **Local-first** — nothing ever leaves your machine unless you explicitly choose a cloud LLM
- **Connected** — every atom is linked to related atoms, its source, and its subject via a graph

## The lattice metaphor

Memories become powerful when they connect. A decision linked to the facts that drove it. A preference linked to the experience that shaped it. Connect enough memories and you get a _lattice_: a structured graph of everything you know, living on your own device.

The graph is what makes Lattice different from a notes app. When you ask "why did I switch to Neovim?", Lattice doesn't just search for "Neovim" — it traverses subject edges, provenance edges, and temporal edges to assemble the full picture from atoms captured months apart.

## The three-layer architecture

| Layer | What it does |
|-------|-------------|
| **Ingest** | Segments text by source type (chat/markdown/code), extracts atoms via LLM, links to graph |
| **Select** | BM25 seeds → dense semantic search → graph BFS expansion — zero LLM calls |
| **Synthesize** | Streams a prose answer with numbered citations from the atom pack |

## What "local-first" means here

- The daemon, web UI, and atom store all run on your machine
- Ollama is the recommended LLM backend — thoughts never leave your device
- For cloud LLMs (OpenRouter/Anthropic), `EntityRedactor` strips names before the API call and restores them after — atoms on disk always contain real names
- No account. No subscription. No vendor lock-in.

## What Lattice is not

- **Not a notes app** — Lattice extracts structure from your thoughts; it doesn't store raw text
- **Not a search engine** — Lattice synthesizes answers, not just retrieves documents
- **Not a cloud service** — there is no hosted Lattice; you run it yourself
- **Not a replacement for Claude/ChatGPT** — Lattice is the memory layer that makes any LLM remember *you specifically*
