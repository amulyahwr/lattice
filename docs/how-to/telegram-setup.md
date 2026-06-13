# Set Up Telegram Bot

The Lattice Telegram bot lets you capture and recall from your phone without opening any app — just send a message to your personal bot.

## Prerequisites

- Lattice daemon running on your laptop
- Python `python-telegram-bot` package: `uv sync --group telegram`
- A Telegram account

## Step 1: Create a bot with BotFather

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a name: e.g. `My Lattice`
4. Choose a username: e.g. `my_lattice_bot` (must end in `bot`)
5. BotFather returns your token: `7123456789:AAF...`

Copy the token — you'll need it in Step 2.

## Step 2: Set the environment variable

```bash
export LATTICE_TELEGRAM_TOKEN=7123456789:AAF...
```

Add this to your shell profile (`.zshrc`, `.bash_profile`) or the launchd plist if using auto-start.

## Step 3: Start the bot

```bash
uv run lattice-telegram
```

The bot starts polling Telegram. Leave it running.

## Step 4: Test it

Open Telegram, find your bot (`@my_lattice_bot`), and send:

```
just decided to use PostgreSQL
```

You should receive:
```
✅ captured
```

Try a recall:
```
what database am I using?
```

You should receive an answer citing your atoms.

## Step 5: Auto-start (optional)

To run the bot automatically at login, see the launchd plist in `extras/dev.lattice.telegram.plist`. You need to add the following env vars to the plist:

```xml
<key>EnvironmentVariables</key>
<dict>
    <key>LLM_PROVIDER</key><string>ollama</string>
    <key>LLM_MODEL</key><string>gemma4</string>
    <key>LLM_API_KEY</key><string>your-key-if-needed</string>
    <key>LLM_BASE_URL</key><string></string>
    <key>LATTICE_DIR</key><string>/Users/yourname/.lattice</string>
    <key>LATTICE_TELEGRAM_TOKEN</key><string>7123456789:AAF...</string>
</dict>
```

!!! warning "launchd doesn't inherit shell env"
    You must set all env vars explicitly in the plist. They are not inherited from your shell profile.

## Commands

| Command | What it does |
|---------|-------------|
| `/start` | Opening strip — streak, recent topics, last question |
| `/ask <question>` | Force recall mode for a query |
| `/status` | Atom count + streak |
| `/journey` | Today's multi-branch capture/recall tree |
| `/reset` | Clear today's conversation history |
| `/save` | Force save current session as atoms |

For capture and recall without commands, just type naturally — the bot uses `classify_intent()` to route automatically.

## When the daemon is down

If your laptop is sleeping or the daemon isn't running, the Telegram bot writes your message to `LATTICE_DIR/inbox/telegram-{chat_id}-{uuid}.txt`. When the daemon restarts, it drains the inbox and ingests queued messages, then sends a follow-up reply via the Telegram API.

## Privacy note

Messages sent to your Telegram bot go to Telegram's servers before reaching your laptop. If you're using Ollama (fully local LLM), Telegram is the only external service your text touches. If you're using a cloud LLM with `LATTICE_PII_SCRUB=true`, PII is stripped before the LLM call and restored before writing to disk.
