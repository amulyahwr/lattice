# Your First Memory

This guide walks you through capturing, finding, and recalling your first atom. By the end you'll understand what Lattice actually does with what you tell it.

## Step 1: Capture a fact

With the daemon running, open the web UI at [localhost:7337](http://localhost:7337) or use the terminal:

```bash
uv run lc "I want to read Thinking Fast and Slow by Kahneman"
```

You'll see a confirmation: `captured: 1 new`.

## Step 2: Look at the atom on disk

```bash
ls ~/.lattice/
```

You'll find a `.md` file — something like `a1b2c3d4.md`. Open it:

```bash
cat ~/.lattice/a1b2c3d4.md
```

```markdown
---
id: a1b2c3d4
kind: goal
subject: reading list
content: Wants to read "Thinking, Fast and Slow" by Daniel Kahneman.
observed_at: 2025-11-14T09:12:00Z
source_id: lc-cli
quality_score: 1.0
tier: stm
---
Wants to read "Thinking, Fast and Slow" by Daniel Kahneman.
```

Lattice didn't just save the raw text. It extracted:

- **kind** — `goal` (a thing you want to do)
- **subject** — `reading list` (what this atom is "about")
- **content** — a clean restatement of the fact

## Step 3: Capture a few more atoms

The recall system works best with a few atoms to link together.

```bash
uv run lc "I read about 20 pages a day on average"
uv run lc "I prefer non-fiction over fiction"
uv run lc "My current book is Meditations by Marcus Aurelius"
```

## Step 4: Ask a question

Open the web UI and type:

```
What am I reading? What should I read next?
```

Lattice will:

1. Search your atoms (BM25 + graph BFS)
2. Find atoms about current book, reading list, reading pace, genre preference
3. Synthesize a prose answer with numbered citations like `[1]`, `[2]`

The answer should mention Meditations as your current book and suggest Thinking Fast and Slow as next, grounded in what you actually told it.

## Step 5: Check the graph

The graph links all your reading-related atoms by subject:

```bash
uv run lattice-daemon status
```

Returns `atom_count: 4` — four atoms, all linked to the `reading list` subject node in the graph.

## What just happened

```
your text
    ↓  segmented (source type = lc-cli)
    ↓  LLM extraction → {kind, subject, content, observed_at}
    ↓  atom written to ~/.lattice/
    ↓  graph updated: atom_has_subject edge → subject:reading list
    ↓  BM25 index rebuilt

your question
    ↓  BM25 seeds: "reading list", "book", "non-fiction"
    ↓  graph BFS: subject:reading list → all 4 atoms
    ↓  LLM synthesis: prose answer with [1][2][3] citations
    ↓  web UI renders answer + source chips
```

## Next steps

- [MCP Setup](mcp-setup.md) — give Claude Code access to your memories
- [Concepts: Atoms](../concepts/atoms.md) — understand all atom fields
- [Telegram Setup](../how-to/telegram-setup.md) — capture from your phone
