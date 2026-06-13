# Capture Channels

Lattice has multiple channels for getting information in. All channels write to the same atom store via the daemon — a thought captured from Telegram and a thought captured from Claude Code land in the same place.

## Channel overview

| Channel | Best for | Requires |
|---------|---------|---------|
| **Web UI** | Typing thoughts at your desk | Browser, daemon running |
| **`lc` CLI** | Quick captures from terminal | Daemon running |
| **MCP (Claude Code)** | Capturing during coding sessions | Claude Code + daemon |
| **Telegram bot** | Capturing from your phone | `uv sync --group telegram`, bot token |
| **Inbox file drop** | Ingesting documents, notes | Daemon running |
| **Browser extension** | Capturing web content | Chrome, daemon running |

## Web UI

Open [localhost:7337](http://localhost:7337). Type in the text box and press Enter.

The web UI runs `classify_intent()` on your input — if it looks like a question it routes to recall; if it looks like a statement it routes to capture. Both paths show in the same chat-style interface.

The web UI also supports:
- File drag-and-drop (PDF, docx, pptx, xlsx, txt, md)
- Multi-turn conversation with context reset detection
- Streaming answers with citations
- Feedback (👍/👎) on answers

## `lc` CLI

```bash
uv run lc "I decided to use PostgreSQL for the project"
```

Single-fact captures from the terminal. Best for quick thoughts while working. Run `lc status` to see atom count + today's activity.

For files:

```bash
uv run lc path/to/meeting-notes.pdf
```

## MCP (Claude Code)

Claude Code calls `lattice_ingest` automatically when you share facts during a conversation. You can also trigger it explicitly:

```
Remember: we're using PostgreSQL with UUID primary keys
```

See [MCP Setup](../getting-started/mcp-setup.md) for configuration.

## Telegram bot

Send a message from your phone to your personal Lattice bot. The bot detects whether it's a capture or recall, routes accordingly, and responds with a confirmation or answer.

```
You: just decided to switch from vim to neovim
Bot: ✅ captured

You: what editor do I use?
Bot: You use Neovim [1]. You switched from Vim recently [2].
```

See [Set Up Telegram Bot](../how-to/telegram-setup.md) for setup.

## Inbox file drop

Drop any `.md` or `.txt` file into `LATTICE_DIR/inbox/`:

```bash
cp ~/Documents/book-notes.md ~/.lattice/inbox/
```

The daemon processes it within seconds and moves it to `processed/`. This is the primary path for ingesting large documents, exported notes, or anything too long to type.

For richer file types (PDF, docx, pptx, xlsx), use the web UI file upload or `lc path/to/file`.

## Browser extension

The Chrome extension adds:
- Right-click → "Save to Lattice" on any selected text
- ⌥⇧S keyboard shortcut
- Popup showing atom count + daemon status indicator

The extension POSTs to `localhost:7337/api/ingest` directly.

## Channel consistency

All channels share the same backend. An atom captured from Telegram can be recalled from the web UI, MCP tools, or any other channel. The `source_id` field on each atom records which channel it came from.

The `chat.jsonl` log records every turn (capture and recall) across all channels, with a `channel` field. This is what powers the journey view in the web UI sidebar and `lc status`.

## `classify_intent()` — how Lattice decides capture vs recall

Channels that receive free-form input (web UI, Telegram, future channels) use `classify_intent()` from `lattice/conversation.py`:

1. **Fast path**: if the query ends with `?`, it's recall
2. **LLM call**: single call to `REFORMULATION_MODEL` → returns `"capture"` or `"recall"`
3. **Fallback**: `"recall"` on error

This means you don't need separate capture/recall commands in most channels — just type naturally.
