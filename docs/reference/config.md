# Config Reference

All configuration is via environment variables. Variables are read once at startup by `Config.from_env()` in `lattice/config.py`. Tests construct `Config(lattice_dir=tmp_path)` directly without env vars.

---

## Required

| Variable | Description |
|----------|-------------|
| `LLM_PROVIDER` | `ollama` or `openai` (use `openai` for OpenRouter, Anthropic, or any OpenAI-compat endpoint) |
| `LLM_MODEL` | Model identifier. For Ollama: `gemma4`, `llama3.2`, etc. For OpenRouter: `google/gemini-2.0-flash-001`, etc. |
| `LATTICE_DIR` | Path to your atom store. Created on first run. Example: `~/.lattice` |

`LLM_API_KEY` is required for all providers **except** `ollama`.

---

## Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `LATTICE_DIR` | `~/.lattice` | Root directory for atoms, graph, logs, socket |
| `LATTICE_SOCK` | `$LATTICE_DIR/daemon.sock` | Unix socket path for IPC |
| `LATTICE_INBOX` | `$LATTICE_DIR/inbox/` | Watch directory for file-drop ingestion |

---

## LLM

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | `ollama` or `openai` |
| `LLM_MODEL` | — | Model name. Required. |
| `LLM_API_KEY` | — | API key. Required for non-Ollama providers. |
| `LLM_BASE_URL` | — | Override the API endpoint. Use for OpenRouter (`https://openrouter.ai/api/v1`), Anthropic (`https://api.anthropic.com/v1`), or any OpenAI-compat endpoint. |
| `LLM_NUM_CTX` | `4096` | Context window size passed to Ollama (`num_ctx`). |
| `INGEST_MODEL` | `$LLM_MODEL` | Model for atom extraction and supersession. Falls back to `LLM_MODEL`. |
| `SYNTHESIS_MODEL` | `$LLM_MODEL` | Model for answer synthesis. Falls back to `LLM_MODEL`. |
| `REFORMULATION_MODEL` | `$INGEST_MODEL` | Model for query reformulation. Falls back to `INGEST_MODEL` → `LLM_MODEL`. |

### Model routing

```
REFORMULATION_MODEL (if set)
    └── INGEST_MODEL (if set)
            └── LLM_MODEL  ← required
```

This lets you use a cheap fast model for reformulation and a more capable model for synthesis.

---

## Web server

| Variable | Default | Description |
|----------|---------|-------------|
| `LATTICE_WEB_HOST` | `127.0.0.1` | Host to bind the web UI server |
| `LATTICE_WEB_PORT` | `7337` | Port for the web UI |

---

## Conversation

| Variable | Default | Description |
|----------|---------|-------------|
| `LATTICE_REFORMULATION` | `1` | Set to `0` or `false` to disable multi-turn query reformulation |
| `LATTICE_CONVERSATION_TURNS` | `2` | Number of previous Q&A turns passed to reformulation |

---

## Selection tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `LATTICE_DENSE_SEEDS` | `false` | Enable dense semantic search (requires `uv sync --group semantic`) |
| `LATTICE_DENSE_TOP_K` | `10` | Number of dense search candidates to merge with BM25 seeds |
| `LATTICE_SEED_MIN_SCORE` | `0.0` | Drop seeds with BM25 score below this threshold |
| `LATTICE_BFS_RESCORE` | `false` | Re-score atoms after graph BFS expansion |
| `LATTICE_RECOMMENDATION_CAP` | `5` | Max atoms returned for `kind=recommendation` queries |
| `LATTICE_POINTED_DOMINANCE` | `0.7` | Source diversity probe: stay single-source when top source ≥ this fraction |
| `LATTICE_TIME_DECAY` | `1` | Set to `0` to disable time-decay re-ranking (useful for debugging) |

---

## Ingest

| Variable | Default | Description |
|----------|---------|-------------|
| `LATTICE_SUBJECT_FUZZY_THRESHOLD` | `80` | RapidFuzz score threshold for subject matching during supersession (0–100) |
| `LATTICE_INGEST_WORKERS` | `1` | Parallel workers for atom extraction (>1 may be unstable with Ollama) |

---

## PII

| Variable | Default | Description |
|----------|---------|-------------|
| `LATTICE_PII_SCRUB` | `true` | Enable PII round-trip redaction before cloud LLM calls. Automatically disabled for `ollama` provider. |
| `LATTICE_NER_MODEL` | `""` | Ollama model to use for named entity recognition. When unset, falls back to regex-only (email + phone) |

---

## Embeddings

| Variable | Default | Description |
|----------|---------|-------------|
| `LATTICE_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | fastembed model for dense semantic search. Only used when `LATTICE_DENSE_SEEDS=true`. |

---

## Telegram

| Variable | Default | Description |
|----------|---------|-------------|
| `LATTICE_TELEGRAM_TOKEN` | — | Your Telegram bot token from BotFather. Required for the Telegram bot. |

---

## Tracing (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `LATTICE_TRACE` | `false` | Write per-query traces to `LATTICE_DIR/traces.jsonl`. Query text is hashed; atom IDs stored but not content. |

---

## Example: minimal Ollama setup

```bash
export LLM_PROVIDER=ollama
export LLM_MODEL=gemma4
export LATTICE_DIR=~/.lattice
```

## Example: OpenRouter with per-stage models

```bash
export LLM_PROVIDER=openai
export LLM_BASE_URL=https://openrouter.ai/api/v1
export LLM_API_KEY=sk-or-...
export LLM_MODEL=google/gemini-2.0-flash-001
export INGEST_MODEL=google/gemini-2.0-flash-001
export SYNTHESIS_MODEL=anthropic/claude-sonnet-4-6
export REFORMULATION_MODEL=google/gemini-2.0-flash-lite
export LATTICE_DIR=~/.lattice
export LATTICE_DENSE_SEEDS=1
```

## Example: fully local with dense search

```bash
export LLM_PROVIDER=ollama
export LLM_MODEL=gemma4
export LATTICE_DIR=~/.lattice
export LATTICE_DENSE_SEEDS=1
export LATTICE_PII_SCRUB=false  # not needed for local-only
```

```bash
uv sync --group semantic  # install fastembed
```
