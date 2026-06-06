"""lattice.telegram_bot: Telegram polling bot for mobile capture."""
from __future__ import annotations

import logging
import os
import re
import uuid

_CITATION_RE = re.compile(r"\[([^\]]*)\]\[src:[^\]]+\]")

log = logging.getLogger("lattice.telegram_bot")

# --- Intent detection --------------------------------------------------------

_QUESTION_STARTERS = re.compile(
    r"^(what|who|where|when|why|how|which|is|are|was|were|do|does|did|"
    r"have|has|had|can|could|will|would|should|remind|tell|show|find|list)\b",
    re.IGNORECASE,
)

_RECALL_PHRASES = re.compile(
    r"\b(remind me|what do i|what did i|have i|do i have|"
    r"what is my|what are my|what was my|tell me about|look up)\b",
    re.IGNORECASE,
)

_CAPTURE_PHRASES = re.compile(
    r"^(i |just |today |yesterday |we |decided |bought |learned |finished |"
    r"started |going to |planning |note:|fyi:|btw:)",
    re.IGNORECASE,
)


def _classify(text: str) -> str:
    """Return 'recall', 'capture', or 'unclear'."""
    t = text.strip()
    if t.endswith("?"):
        return "recall"
    if _QUESTION_STARTERS.match(t):
        return "recall"
    if _RECALL_PHRASES.search(t):
        return "recall"
    if _CAPTURE_PHRASES.match(t):
        return "capture"
    return "unclear"


# --- Feedback ----------------------------------------------------------------

_THUMBS_UP   = {"👍", "yes", "good", "great", "helpful", "y", "up"}
_THUMBS_DOWN = {"👎", "no", "bad", "wrong", "unhelpful", "n", "down"}
_REASON_MAP  = {
    "wrong sources": "wrong_sources",
    "wrong source":  "wrong_sources",
    "inaccurate":    "inaccurate",
    "incorrect":     "inaccurate",
    "incomplete":    "incomplete",
    "missing":       "incomplete",
    "off topic":     "off_topic",
    "irrelevant":    "off_topic",
}


def _post_feedback(question: str, answer: str, rating: str, reason: str | None = None) -> None:
    import json
    import urllib.request
    port = os.environ.get("LATTICE_WEB_PORT", "7337")
    url = f"http://127.0.0.1:{port}/api/feedback"
    payload = json.dumps({"question": question, "answer": answer, "rating": rating, "reason": reason}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # feedback is non-critical


def _match_reason(text: str) -> str | None:
    t = text.lower().strip()
    for phrase, code in _REASON_MAP.items():
        if phrase in t:
            return code
    return None


_MILESTONE_MESSAGES = {
    1:  "First recall. Good start.",
    7:  "A week in. Lattice is starting to know you.",
    30: "30 days. You've built something here.",
}


def _milestone_message(streak: int, atom_count: int = 0) -> str | None:
    """Return a milestone message if streak is a milestone, else None."""
    if streak == 14:
        return f"Two weeks of asking and remembering. You have {atom_count} things stored — this is becoming real."
    return _MILESTONE_MESSAGES.get(streak)


def _get_streak_info() -> tuple[int, bool, int]:
    """Fetch (streak, grace_day_active, atom_count) from web API. Returns (0, False, 0) on failure."""
    import json
    import urllib.request as _ur
    port = os.environ.get("LATTICE_WEB_PORT", "7337")
    try:
        with _ur.urlopen(f"http://127.0.0.1:{port}/api/usage/summary", timeout=3) as r:
            data = json.loads(r.read())
            return data.get("streak", 0), data.get("grace_day_active", False), data.get("atom_count", 0)
    except Exception:
        return 0, False, 0


def _get_weekly_summary() -> dict | None:
    """Fetch weekly report data. Returns None on failure."""
    import json
    import urllib.request as _ur
    port = os.environ.get("LATTICE_WEB_PORT", "7337")
    try:
        with _ur.urlopen(f"http://127.0.0.1:{port}/api/usage/weekly", timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _get_topic_depth(subject: str) -> int:
    """Return atom count for a subject. Returns 0 on failure."""
    import json
    import urllib.request as _ur
    port = os.environ.get("LATTICE_WEB_PORT", "7337")
    try:
        url = f"http://127.0.0.1:{port}/api/topic/depth?subject={subject}"
        with _ur.urlopen(url, timeout=3) as r:
            return json.loads(r.read()).get("count", 0)
    except Exception:
        return 0


_DEPTH_THRESHOLDS = [
    (20, "This is one of the things you know best."),
    (10, "You've thought about this a lot."),
    (5,  "That's a topic you know well."),
]


def _topic_depth_message(subject: str, count: int) -> str | None:
    for threshold, label in _DEPTH_THRESHOLDS:
        if count >= threshold:
            return f"You've saved {count} things about {subject}. {label}"
    return None


# --- Helpers -----------------------------------------------------------------

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


def _is_allowed(update) -> bool:
    allowed = _allowed_ids()
    if not allowed:
        return True
    user_id = update.effective_user.id if update.effective_user else None
    return user_id in allowed


def _inbox_fallback(text: str, chat_id: int) -> None:
    from lattice.config import Config
    inbox = Config.from_env().inbox_dir
    inbox.mkdir(parents=True, exist_ok=True)
    fname = f"telegram-{chat_id}-{uuid.uuid4().hex[:8]}.txt"
    (inbox / fname).write_text(text, encoding="utf-8")
    log.info("telegram: queued to inbox as %s", fname)


def _append_history(context, role: str, text: str) -> None:
    context.chat_data.setdefault("history", []).append({"role": role, "text": text})


async def _do_capture(update, context, text: str) -> None:
    chat_id = update.effective_chat.id
    try:
        from lattice.client import DaemonClient
        from lattice.db import LatticeDB
        from lattice.config import Config
        client = DaemonClient()
        atom_ids = client.ingest(text, source_id="telegram")
        n = len(atom_ids)
        if n == 0:
            await update.message.reply_text("Got it — nothing new to add, looks like this is already in there.")
        else:
            _append_history(context, "user", text)
            await update.message.reply_text(f"Saved. {n} new thing{'s' if n != 1 else ''} added to your memory.")
            # Topic depth check for newly created atoms
            try:
                db = LatticeDB(Config.from_env().lattice_dir)
                subjects_checked: set[str] = set()
                for aid in atom_ids:
                    try:
                        atom = db.read(aid)
                        subject = atom.subject
                        if not subject or subject in subjects_checked:
                            continue
                        subjects_checked.add(subject)
                        depth_key = f"topic_depth_{subject.lower().strip()}"
                        if context.bot_data.get(depth_key):
                            continue
                        count = _get_topic_depth(subject)
                        msg = _topic_depth_message(subject, count)
                        if msg:
                            context.bot_data[depth_key] = True
                            await update.message.reply_text(msg)
                    except Exception:
                        pass
            except Exception:
                pass
    except (RuntimeError, OSError):
        _inbox_fallback(text, chat_id)
        await update.message.reply_text("Lattice is offline right now. Your message is safe — I'll confirm once it's processed. 📥")


async def _do_recall(update, context, question: str) -> None:
    import json
    import urllib.request
    from lattice.config import Config

    cfg = Config.from_env()
    url = f"http://127.0.0.1:{os.environ.get('LATTICE_WEB_PORT', '7337')}/api/answer"
    payload = json.dumps({"question": question}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())
        answer = body.get("answer")
        if not answer:
            await update.message.reply_text("Nothing stored about that yet.")
            return

        # Collect unique source labels, strip markers from prose
        labels: list[str] = []
        seen: set[str] = set()
        def _collect(m: re.Match) -> str:
            label = m.group(1).strip()
            if label and label not in seen:
                seen.add(label)
                labels.append(label)
            return ""

        clean = _CITATION_RE.sub(_collect, answer).strip()
        if labels:
            sources = "\n".join(f"· {l}" for l in labels)
            clean = f"{clean}\n\nSources:\n{sources}"

        # Rediscovery: note if any cited atom is ≥30 days old
        from datetime import datetime, timezone as _tz
        _now = datetime.now(_tz.utc)
        old_days: list[int] = []
        for atom_meta in body.get("atoms", []):
            ia = atom_meta.get("ingested_at")
            if not ia:
                continue
            try:
                ts = datetime.fromisoformat(ia.replace("Z", "+00:00"))
                days = (_now - ts).days
                if days >= 30:
                    old_days.append(days)
            except Exception:
                pass
        if old_days:
            oldest = max(old_days)
            clean = f"{clean}\n\n_One of these memories is from {oldest} days ago._"

        _append_history(context, "user", question)
        _append_history(context, "assistant", clean)

        # Milestone moment — prepend once per milestone day, once per session
        streak, _, atom_count = _get_streak_info()
        milestone_key = f"milestone_shown_{streak}"
        if streak > 0 and not context.bot_data.get(milestone_key):
            msg = _milestone_message(streak, atom_count)
            if msg:
                context.bot_data[milestone_key] = True
                await update.message.reply_text(msg)

        for i in range(0, len(clean), 4096):
            await update.message.reply_text(clean[i:i + 4096])
        # Only ask for feedback on uncertain answers (≤1 atom = low confidence)
        if body.get("atom_count", 0) <= 1:
            context.chat_data["pending_feedback"] = {"question": question, "answer": clean}
            await update.message.reply_text("Was this helpful? Reply 👍 or 👎")
    except Exception:
        log.exception("recall error")
        await update.message.reply_text("Lattice is offline right now. Try again in a moment.")


# --- Handlers ----------------------------------------------------------------

def _spark_question(atom) -> str:
    subject = atom.subject or "that"
    if atom.kind == "decision":
        return f"What did I decide about {subject}?"
    if atom.kind == "preference":
        return f"What do I prefer about {subject}?"
    return f"Tell me about {subject}"


async def _handle_start(update, context) -> None:
    if not _is_allowed(update):
        return
    from lattice.config import Config
    from lattice.db import LatticeDB
    cfg = Config.from_env()
    db = LatticeDB(cfg.lattice_dir)
    atoms = [a for a in db.all() if not a.is_superseded]
    if atoms:
        suggestions = "\n".join(f"· {_spark_question(a)}" for a in atoms[:3])
        body = (
            "Hey — just send me anything worth keeping. "
            "A thought, a decision, something you don't want to forget.\n\n"
            f"You could ask:\n{suggestions}\n\n"
            "Or just send me a thought and I'll save it.\n\n"
            "/ask <question> — recall anything\n"
            "/save — capture this session\n"
            "/status — memory count"
        )
    else:
        body = (
            "Hey, good to have you here.\n\n"
            "Send me anything worth keeping — a decision you made, something you learned, "
            "a preference you want to remember. I'll hold onto it and surface it when you need it.\n\n"
            "What's on your mind?"
        )
    await update.message.reply_text(body)


async def _send_weekly_summary_if_due(update, context) -> None:
    """Prepend weekly summary on first Monday interaction. Stored in bot_data to survive restarts."""
    from datetime import datetime, timezone as _tz
    now = datetime.now(_tz.utc)
    if now.weekday() != 0:  # Monday = 0
        return
    week_key = f"weekly_report_{now.isocalendar()[0]}_{now.isocalendar()[1]}"
    if context.bot_data.get(week_key):
        return
    data = _get_weekly_summary()
    if not data or data.get("streak", 0) < 7:
        return
    context.bot_data[week_key] = True
    parts = [f"{data['atoms_this_week']} things saved", f"{data['recalls_this_week']} questions asked", f"{data['topics_this_week']} topics"]
    msg = "This week — " + ", ".join(parts)
    if data.get("top_topic"):
        msg += f". Most on your mind: {data['top_topic']}"
    if data.get("new_topics"):
        msg += f". Something new: {data['new_topics'][0]}"
    await update.message.reply_text(msg)


async def _handle_message(update, context) -> None:
    if not _is_allowed(update):
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    # Weekly summary on first Monday interaction (non-critical, never blocks)
    try:
        await _send_weekly_summary_if_due(update, context)
    except Exception:
        pass

    # Check if we're waiting for a feedback rating reply
    pending_fb = context.chat_data.get("pending_feedback")
    if pending_fb:
        reply = text.lower().strip()
        if reply in _THUMBS_UP:
            del context.chat_data["pending_feedback"]
            _post_feedback(pending_fb["question"], pending_fb["answer"], "up")
            await update.message.reply_text("Thanks! 👍")
            return
        elif reply in _THUMBS_DOWN:
            context.chat_data["pending_feedback"]["rating"] = "down"
            await update.message.reply_text(
                "What went wrong? Reply:\n"
                "wrong sources · inaccurate · incomplete · off topic"
            )
            return
        elif "rating" in pending_fb:
            # waiting for reason after 👎
            reason = _match_reason(reply)
            _post_feedback(pending_fb["question"], pending_fb["answer"], "down", reason)
            del context.chat_data["pending_feedback"]
            await update.message.reply_text("Got it, thanks.")
            return
        else:
            # not a feedback reply — drop pending feedback, process normally
            del context.chat_data["pending_feedback"]

    # Check if we're waiting for a clarification reply
    pending = context.chat_data.get("pending_text")
    if pending:
        reply = text.lower().strip()
        if reply in ("save", "capture", "s"):
            del context.chat_data["pending_text"]
            await _do_capture(update, context, pending)
            return
        elif reply in ("ask", "recall", "look up", "a", "r"):
            del context.chat_data["pending_text"]
            await _do_recall(update, context, pending)
            return
        else:
            # Not a clarification — treat new message normally, drop pending
            del context.chat_data["pending_text"]

    intent = _classify(text)

    if intent == "recall":
        await _do_recall(update, context, text)
    elif intent == "capture":
        await _do_capture(update, context, text)
    else:
        # Ambiguous — ask user to clarify
        context.chat_data["pending_text"] = text
        await update.message.reply_text(
            "Save this to memory or look something up?\n\nReply save or ask."
        )


async def _handle_ask(update, context) -> None:
    if not _is_allowed(update):
        return
    question = " ".join(context.args).strip() if context.args else ""
    if not question:
        await update.message.reply_text("What would you like to know? Usage: /ask <question>")
        return
    await _do_recall(update, context, question)


async def _handle_save(update, context) -> None:
    if not _is_allowed(update):
        return
    history = context.chat_data.get("history", [])
    if not history:
        await update.message.reply_text("Nothing to save from this session yet.")
        return
    chunk = "\n".join(f"{h['role']}: {h['text']}" for h in history)
    try:
        from lattice.client import DaemonClient
        atom_ids = DaemonClient().ingest(chunk, source_id="telegram")
        context.chat_data["history"] = []
        n = len(atom_ids)
        if n == 0:
            await update.message.reply_text("Session saved — nothing new to add, looks like it's all already in there.")
        else:
            await update.message.reply_text(f"Session saved. {n} new thing{'s' if n != 1 else ''} added to your memory.")
    except (RuntimeError, OSError):
        await update.message.reply_text("Lattice is offline right now. Try again in a moment.")


async def _handle_status(update, context) -> None:
    if not _is_allowed(update):
        return
    try:
        import urllib.request as _ur
        import json as _json
        from lattice.db import LatticeDB
        from lattice.config import Config
        cfg = Config.from_env()
        db = LatticeDB(cfg.lattice_dir)
        count = len([a for a in db.all() if not a.is_superseded])

        # Fetch streak from web API (handles grace day logic centrally)
        streak = 0
        grace = False
        try:
            url = f"http://127.0.0.1:{os.environ.get('LATTICE_WEB_PORT', '7337')}/api/usage/summary"
            with _ur.urlopen(url, timeout=3) as r:
                summary = _json.loads(r.read())
                streak = summary.get("streak", 0)
                grace = summary.get("grace_day_active", False)
        except Exception:
            pass

        parts = [f"{count} memories"]
        if streak > 0:
            depth = "day deep" if streak == 1 else "days deep"
            streak_str = f"{streak} {depth}"
            if grace:
                streak_str += " · rest day"
            parts.append(streak_str)

        await update.message.reply_text(" · ".join(parts))
    except Exception:
        await update.message.reply_text("Couldn't reach your Lattice store. Try again in a moment.")


async def _handle_non_text(update, context) -> None:
    if not _is_allowed(update):
        return
    await update.message.reply_text("I can only handle text for now — just type it out and I'll save it.")


# --- Entry point -------------------------------------------------------------

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
    app.add_handler(CommandHandler("ask", _handle_ask))
    app.add_handler(CommandHandler("save", _handle_save))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))
    app.add_handler(MessageHandler(~filters.TEXT, _handle_non_text))

    log.info("Telegram bot starting (polling mode)")
    app.run_polling(
        drop_pending_updates=False,
        bootstrap_retries=-1,
        timeout=30,
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
