"""lattice.telegram_bot: Telegram polling bot for mobile capture."""
from __future__ import annotations

import logging
import os
import uuid

log = logging.getLogger("lattice.telegram_bot")


def _allowed_ids() -> set[int]:
    raw = os.environ.get("LATTICE_TELEGRAM_ALLOWED_IDS", "")
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            try:
                ids.add(int(part))
            except ValueError:
                log.warning("invalid LATTICE_TELEGRAM_ALLOWED_IDS entry: %r", part)
    return ids


def _inbox_fallback(text: str, chat_id: int) -> None:
    from lattice.config import Config
    inbox = Config.from_env().inbox_dir
    inbox.mkdir(parents=True, exist_ok=True)
    fname = f"telegram-{chat_id}-{uuid.uuid4().hex[:8]}.txt"
    (inbox / fname).write_text(text, encoding="utf-8")
    log.info("telegram: queued to inbox as %s", fname)


def _is_allowed(update) -> bool:
    allowed = _allowed_ids()
    if not allowed:
        return True  # no allowlist = accept everyone (not recommended)
    user_id = update.effective_user.id if update.effective_user else None
    return user_id in allowed


async def _handle_start(update, context) -> None:
    if not _is_allowed(update):
        return
    await update.message.reply_text(
        "Hey — just send me anything worth keeping. "
        "A thought, a decision, something you don't want to forget. I've got it.\n\n"
        "/status to see what's stored."
    )


async def _handle_message(update, context) -> None:
    if not _is_allowed(update):
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    chat_id = update.effective_chat.id

    try:
        from lattice.client import DaemonClient
        atom_ids = DaemonClient().ingest(text, source_id="telegram")
        n = len(atom_ids)
        if n == 0:
            await update.message.reply_text("Got it — nothing new to add, looks like this is already in there.")
        else:
            await update.message.reply_text(f"Saved. {n} new thing{'s' if n != 1 else ''} added to your memory.")
    except (RuntimeError, OSError):
        _inbox_fallback(text, chat_id)
        await update.message.reply_text("Lattice is offline right now. Your message is safe — I'll confirm once it's processed. 📥")


async def _handle_status(update, context) -> None:
    if not _is_allowed(update):
        return
    try:
        from lattice.db import LatticeDB
        from lattice.config import Config
        db = LatticeDB(Config.from_env().lattice_dir)
        count = len([a for a in db.all() if not a.is_superseded])
        await update.message.reply_text(f"{count} things in your memory right now.")
    except Exception:
        await update.message.reply_text("Couldn't reach your Lattice store. Try again in a moment.")


async def _handle_non_text(update, context) -> None:
    if not _is_allowed(update):
        return
    await update.message.reply_text("I can only handle text for now — just type it out and I'll save it.")


def run(token: str) -> None:
    try:
        from telegram.ext import Application, CommandHandler, MessageHandler, filters
    except ImportError:
        raise SystemExit(
            "python-telegram-bot not installed. Run: uv sync --group telegram"
        )

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(CommandHandler("status", _handle_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))
    app.add_handler(MessageHandler(~filters.TEXT, _handle_non_text))

    log.info("Telegram bot starting (polling mode)")
    app.run_polling(
        drop_pending_updates=False,  # process queued messages after restart
        bootstrap_retries=-1,        # retry forever on startup network error
        timeout=30,                  # long-poll timeout — fewer requests, faster delivery
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.environ.get("LATTICE_TELEGRAM_TOKEN", "").strip()
    if not token:
        print("LATTICE_TELEGRAM_TOKEN not set", flush=True)
        raise SystemExit(1)
    run(token)


if __name__ == "__main__":
    main()
