# HTTP API Reference

The Lattice web server exposes a REST API at `http://localhost:7337`. All endpoints accept and return JSON unless noted.

---

## Capture

### `POST /api/ingest`

Capture text to memory.

**Request:**
```json
{
  "text": "I decided to use PostgreSQL",
  "source_id": "web",
  "metadata": {
    "observed_at": "2025-11-14T09:12:00Z"
  }
}
```

**Response:**
```json
{
  "atoms_new": 1,
  "atoms_updated": 0,
  "duplicates_skipped": 0,
  "atom_ids": ["a1b2c3d4"]
}
```

---

### `POST /api/ingest-file`

Upload a file for ingestion. Multipart form data.

**Request:** `multipart/form-data` with field `file`.

Supported types: `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.xls`, `.md`, `.txt`

**Response:** same as `/api/ingest`

---

### `POST /api/capture-log`

Write a capture turn to `chat.jsonl` from an external channel (Telegram, etc.) without re-ingesting.

**Request:**
```json
{
  "question": "just switched to neovim",
  "reformulated_query": "Switched from Vim to Neovim.",
  "session_id": "sess_20251114",
  "channel": "telegram"
}
```

---

## Recall

### `POST /api/query`

Streaming SSE synthesis (web UI path).

**Request:**
```json
{
  "question": "what coffee do I like?",
  "conversation_history": [
    {"role": "user", "content": "what do I eat for breakfast?"},
    {"role": "assistant", "content": "You usually have oatmeal [1]."}
  ],
  "session_id": "sess_20251114"
}
```

**Response:** `text/event-stream`

Events emitted:
```
event: atoms
data: {"atoms": [...], "query_topic": "coffee preference", "context_reset": false}

event: token
data: {"token": "You prefer "}

event: token
data: {"token": "Ethiopian dark roast"}

event: done
data: {"pii_protected": false}
```

If `classify_intent()` routes to capture, emits:
```
event: captured
data: {"atoms_new": 1, "atoms_updated": 0, "atom_ids": ["a1b2c3"]}
```

---

### `POST /api/answer`

Blocking JSON synthesis (Telegram / programmatic path).

**Request:**
```json
{
  "question": "what coffee do I like?",
  "conversation_history": []
}
```

**Response:**
```json
{
  "answer": "You prefer Ethiopian dark roast coffee [1].",
  "atoms": [...],
  "pii_protected": false,
  "context_reset": false
}
```

---

## Chat history

### `GET /api/chat/recent?n=10`

Last N Q&A turns across all channels. Used for page-reload restore and opening strip.

**Response:** `{"turns": [...]}`

---

### `GET /api/chat/today`

Today's `chat.jsonl` entries across all channels.

**Response:** `{"turns": [...]}`

---

### `POST /api/chat/clear-today`

Remove today's entries from `chat.jsonl`. Shared by web UI clear button, Telegram `/reset`, and `lc clear`.

**Response:** `{"ok": true}`

---

## Atoms

### `GET /api/atoms/recent?n=20`

Recent non-superseded atoms.

**Response:** `{"atoms": [...]}`

---

### `GET /api/atoms/related?atom_id=a1b2c3&limit=5`

BFS from cited atom's subjects → top-N related subjects. Used for curiosity chips ("You also know about…").

**Response:** `{"subjects": ["morning routine", "sleep tracking"]}`

---

## Usage and stats

### `GET /api/usage/summary`

Streak, query counts, average latency, atom count.

**Response:**
```json
{
  "streak_days": 12,
  "total_queries": 89,
  "avg_latency_ms": 1420,
  "atom_count": 147
}
```

---

### `GET /api/usage/weekly`

Weekly report data: atoms, recalls, topics, new topics.

---

### `GET /api/topic/depth?subject=coffee+preference`

Atom count for a given subject. Used for topic depth annotation below answers.

**Response:** `{"subject": "coffee preference", "count": 4}`

---

## Feedback

### `POST /api/feedback`

Record thumbs up/down on an answer.

**Request:**
```json
{
  "ts": "2025-11-14T09:15:00Z",
  "question": "what coffee do I like?",
  "answer": "You prefer Ethiopian dark roast [1].",
  "rating": 1,
  "reason": null,
  "atom_ids": ["a1b2c3"],
  "dismissed_atom_ids": [],
  "citation_map": {"1": "a1b2c3"}
}
```

`rating`: `1` = 👍, `-1` = 👎, `0` = dismissed without rating

---

## System

### `GET /api/health`

Liveness check.

**Response:** `{"ok": true}`

---

### `GET /api/auto-save/status`

Whether the auto-save sweep is currently running.

**Response:** `{"running": false}`
