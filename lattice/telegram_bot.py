"""lattice.telegram_bot: Telegram polling bot for mobile capture."""
from __future__ import annotations

import logging
import os
import re
import uuid

_CITATION_RE = re.compile(r"\[src:([^\]]+)\]")

log = logging.getLogger("lattice.telegram_bot")

# --- Intent detection --------------------------------------------------------
# Shared LLM-based classifier from conversation.py — no regex, handles all NL variations.


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


def _post_feedback(question: str, answer: str, rating: str, reason: str | None = None, atom_ids: list | None = None) -> None:
    import json
    import urllib.request
    port = os.environ.get("LATTICE_WEB_PORT", "7337")
    url = f"http://127.0.0.1:{port}/api/feedback"
    payload = json.dumps({"question": question, "answer": answer, "rating": rating, "reason": reason, "atom_ids": atom_ids or []}).encode()
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


def _get_related_subjects(subjects: list[str], limit: int = 3) -> list[str]:
    """Return related subjects via BFS graph expansion. Returns [] on failure."""
    import json
    import urllib.request as _ur
    port = os.environ.get("LATTICE_WEB_PORT", "7337")
    try:
        q = ",".join(subjects)
        url = f"http://127.0.0.1:{port}/api/atoms/related?subjects={q}&limit={limit}"
        with _ur.urlopen(url, timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return []


def _get_last_question() -> str | None:
    """Return the most recent question from chat.jsonl across all days and channels."""
    import json
    import urllib.request as _ur
    port = os.environ.get("LATTICE_WEB_PORT", "7337")
    try:
        url = f"http://127.0.0.1:{port}/api/chat/recent?limit=1"
        with _ur.urlopen(url, timeout=3) as r:
            records = json.loads(r.read())
            return records[-1].get("question") if records else None
    except Exception:
        return None


def _get_today_turns(channel: str | None = "telegram") -> list[dict]:
    """Return today's chat.jsonl entries. channel=None returns all channels."""
    import json
    import urllib.request as _ur
    port = os.environ.get("LATTICE_WEB_PORT", "7337")
    try:
        url = f"http://127.0.0.1:{port}/api/chat/today"
        if channel:
            url += f"?channel={channel}"
        with _ur.urlopen(url, timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return []




def _get_journey_branches(turns: list[dict]) -> list[dict]:
    """Build journey branch list from today's turns — shared by text tree and opening strip.

    Mirrors web UI _buildJourneyFromTurns exactly: context_reset flag, follow-up
    detection, possessive folding (label contains existing branch name).
    """
    branches: list[dict] = []
    for t in turns:
        question      = t.get("question", "")
        subjects      = t.get("subjects") or []
        context_reset = t.get("context_reset", None)

        query_topic = t.get("query_topic") or None
        is_followup = (context_reset is False) or \
                      (context_reset is None and not query_topic and bool(branches))

        if is_followup and branches:
            if not query_topic:
                branches[-1]["queries"].append(question)
                continue
            cur = branches[-1]
            topic_lower = query_topic.lower().strip()
            cur_lower = cur["subject"].lower().strip()
            if topic_lower.find(cur_lower) != -1 or cur_lower.find(topic_lower) != -1:
                cur["queries"].append(question)
                continue
            # topic doesn't match current branch — fall through to find/create correct branch

        label = query_topic or (subjects[0] if subjects else None)
        if not label:
            continue

        label_lower = label.lower().strip()
        overlap = next(
            (b for b in branches if label_lower.find(b["subject"].lower().strip()) != -1),
            None,
        )
        if overlap:
            overlap["queries"].append(question)
        else:
            branches.append({"subject": label, "queries": [question]})

    return branches


def _build_journey_text(turns: list[dict]) -> str:
    """Render today's journey as indented text tree."""
    branches = _get_journey_branches(turns)
    if not branches:
        return ""
    lines = []
    for b in branches:
        lines.append(f"● {b['subject']}")
        for q in b["queries"]:
            short = q[:50] + "…" if len(q) > 50 else q
            lines.append(f"   └── {short}")
    return "\n".join(lines)


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
        from lattice.conversation import reformulate_capture
        cfg = Config.from_env()
        qa_history = context.chat_data.get("qa_history", [])
        text_to_ingest = reformulate_capture(text, qa_history, cfg)
        client = DaemonClient()
        result = client.ingest_full(
            text_to_ingest, source_id="telegram",
            metadata={"observed_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()},
        )
        atom_ids = result.get("atom_ids", [])
        added   = result.get("atoms_new", 0)
        updated = result.get("atoms_updated", 0)
        # Log to chat.jsonl for audit trail
        try:
            import urllib.request as _ur, json as _json
            port = os.environ.get("LATTICE_WEB_PORT", "7337")
            payload = _json.dumps({
                "question": text,
                "reformulated_query": text_to_ingest if text_to_ingest != text else None,
                "answer": f"[captured: {added} new, {updated} updated]",
                "atom_ids": atom_ids,
                "channel": "telegram",
                "context_reset": False,
            }).encode()
            req = _ur.Request(f"http://127.0.0.1:{port}/api/capture-log",
                              data=payload, headers={"Content-Type": "application/json"}, method="POST")
            _ur.urlopen(req, timeout=2)
        except Exception:
            pass
        if added == 0 and updated == 0:
            await update.message.reply_text("Got it — nothing new to add, looks like this is already in there.")
        else:
            _append_history(context, "user", text)
            parts = []
            if added:   parts.append(f"{added} new thing{'s' if added != 1 else ''}")
            if updated: parts.append(f"{updated} updated")
            await update.message.reply_text(f"Saved. {', '.join(parts)}.")
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
    # Build Q&A history from per-chat buffer (last cfg.conversation_turns pairs)
    raw_history = context.chat_data.get("qa_history", [])
    turns = cfg.conversation_turns
    conv_history = [
        {"question": h["question"], "answer": h["answer"]}
        for h in raw_history[-turns:]
    ]
    payload = json.dumps({
        "question": question,
        "conversation_history": conv_history,
        "session_id": f"telegram-{update.effective_chat.id}",
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())
        answer = body.get("answer")
        if not answer:
            await update.message.reply_text("Nothing stored about that yet.")
            return

        # Build src_key → atom metadata index
        atom_index: dict[str, dict] = {}
        for am in body.get("atoms", []):
            if am.get("src_key"):
                atom_index[am["src_key"]] = am
            if am.get("atom_id"):
                atom_index[am["atom_id"]] = am

        def _channel(source_id: str) -> str:
            if not source_id:
                return ""
            return re.sub(r"^(pdf|pptx|xlsx|xls|docx):", "", source_id)

        def _age(ingested_at: str) -> str:
            if not ingested_at:
                return ""
            try:
                from datetime import datetime, timezone as _tzl
                ts = datetime.fromisoformat(ingested_at.replace("Z", "+00:00"))
                days = (datetime.now(_tzl.utc) - ts).days
                if days < 1: return "today"
                if days == 1: return "yesterday"
                if days < 14: return f"{days}d ago"
                if days < 60: return f"{round(days/7)}w ago"
                return f"{round(days/30)}mo ago"
            except Exception:
                return ""

        # Replace [src:N] with [citation_number] and build numbered sources list
        citation_order: list[str] = []
        seen_ids: set[str] = set()

        def _collect(m: re.Match) -> str:
            src_id = m.group(1)
            if src_id not in atom_index:
                return ""
            if src_id not in seen_ids:
                seen_ids.add(src_id)
                citation_order.append(src_id)
            num = citation_order.index(src_id) + 1
            return f"[{num}]"

        clean = _CITATION_RE.sub(_collect, answer).strip()
        if citation_order:
            # Store full source detail for /sources on-demand
            stored = []
            for src_id in citation_order:
                am = atom_index[src_id]
                num = citation_order.index(src_id) + 1
                preview = (am.get("content_preview") or am.get("subject") or "").strip()
                if len(preview) == 80:
                    preview += "…"
                ch = _channel(am.get("source_id", ""))
                age = _age(am.get("ingested_at", ""))
                stored.append({"num": num, "preview": preview, "channel": ch, "age": age})
            context.chat_data["last_sources"] = stored

            # Compact footer: deduplicated channel names + count
            seen_ch: list[str] = []
            for src_id in citation_order:
                ch = _channel(atom_index[src_id].get("source_id", ""))
                if ch and ch not in seen_ch:
                    seen_ch.append(ch)
            n = len(citation_order)
            footer_channels = " · ".join(seen_ch[:3])
            if len(seen_ch) > 3:
                footer_channels += f" · +{len(seen_ch) - 3} more"
            clean = f"{clean}\n\n📚 {n} source{'s' if n != 1 else ''} · {footer_channels}\n/sources for details"

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

        if body.get("pii_protected"):
            clean = f"{clean}\n\n🔒 _PII protected_"

        _append_history(context, "user", question)
        _append_history(context, "assistant", clean)
        # Q&A buffer for multi-turn reformulation
        if body.get("context_reset"):
            context.chat_data["qa_history"] = []
        context.chat_data.setdefault("qa_history", []).append({"question": question, "answer": clean})

        for i in range(0, len(clean), 4096):
            await update.message.reply_text(clean[i:i + 4096])
        cited_ids = [a.get("atom_id") for a in body.get("atoms", []) if a.get("atom_id")]
        context.chat_data["pending_feedback"] = {"question": question, "answer": clean, "atom_ids": cited_ids}
        await update.message.reply_text("Was this helpful? Reply 👍 or 👎")

        # Curiosity footer
        cited_subjects = [a.get("subject") for a in body.get("atoms", []) if a.get("subject")]
        cited_subjects = list(dict.fromkeys(cited_subjects))[:5]
        if cited_subjects:
            related = _get_related_subjects(cited_subjects, limit=3)
            if related:
                chips = " · ".join(related)
                await update.message.reply_text(f"You also know about: {chips}\n\nUse /ask <topic> to explore.")
    except Exception:
        log.exception("recall error")
        await update.message.reply_text("Lattice is offline right now. Try again in a moment.")


# --- Handlers ----------------------------------------------------------------


async def _handle_start(update, context) -> None:
    if not _is_allowed(update):
        return
    body = (
        "Hey — send me anything worth keeping, or ask about what you've saved.\n\n"
        "/ask <question> — recall anything\n"
        "/journey — today's topic path\n"
        "/reset — clear today's journey\n"
        "/status — memory count + streak\n"
        "/sources — sources from last answer"
    )
    await update.message.reply_text(body)
    await _send_opening_strip_if_due(update, context)


async def _send_opening_strip_if_due(update, context) -> None:
    """Prepend daily opening strip on first interaction of the day."""
    from datetime import datetime, timezone as _tz
    today = datetime.now(_tz.utc).date().isoformat()
    day_key = f"opening_strip_{today}"
    if context.bot_data.get(day_key):
        return
    context.bot_data[day_key] = True

    streak, _, atom_count = _get_streak_info()
    today_turns = _get_today_turns(channel=None)  # all channels — one continuous journey

    parts: list[str] = []
    if streak > 0:
        parts.append(f"{streak} day{'s' if streak != 1 else ''} deep")
    if atom_count > 0:
        parts.append(f"{atom_count} things saved")

    # Topics come from journey branch subjects — same source as /journey command.
    # This guarantees "Amulya" not "Amulya Gupta" (atom subject vs query extraction).
    branches = _get_journey_branches(today_turns)
    seen = [b["subject"] for b in reversed(branches)][:3]

    msg_parts: list[str] = []
    if parts:
        msg_parts.append(" · ".join(parts))
    if seen:
        msg_parts.append(f"Today you've been thinking about: {', '.join(seen)}")
    last_q = _get_last_question()
    if last_q:
        short = last_q[:70] + "…" if len(last_q) > 70 else last_q
        msg_parts.append(f'Last: "{short}"')
    if not msg_parts:
        return
    try:
        await update.message.reply_text("\n".join(msg_parts))
    except Exception:
        pass


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

    # Weekly summary on first text interaction (non-critical); opening strip fires on /start
    try:
        await _send_weekly_summary_if_due(update, context)
    except Exception:
        pass
    # Fallback: if user skipped /start, still show opening strip once
    try:
        await _send_opening_strip_if_due(update, context)
    except Exception:
        pass

    # Check if we're waiting for a feedback rating reply
    pending_fb = context.chat_data.get("pending_feedback")
    if pending_fb:
        reply = text.lower().strip()
        if reply in _THUMBS_UP:
            del context.chat_data["pending_feedback"]
            _post_feedback(pending_fb["question"], pending_fb["answer"], "up", atom_ids=pending_fb.get("atom_ids"))
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
            _post_feedback(pending_fb["question"], pending_fb["answer"], "down", reason, atom_ids=pending_fb.get("atom_ids"))
            del context.chat_data["pending_feedback"]
            await update.message.reply_text("Got it, thanks.")
            return
        else:
            # not a feedback reply — drop pending feedback, process normally
            del context.chat_data["pending_feedback"]

    from lattice.config import Config
    from lattice.conversation import classify_intent
    cfg = Config.from_env()
    intent = classify_intent(text, cfg)

    if intent == "recall":
        await _do_recall(update, context, text)
    else:
        await _do_capture(update, context, text)


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
        result = DaemonClient().ingest_full(chunk, source_id="telegram"); atom_ids = result.get("atom_ids", [])
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

        # Auto-save status
        try:
            url = f"http://127.0.0.1:{os.environ.get('LATTICE_WEB_PORT', '7337')}/api/auto-save/status"
            with _ur.urlopen(url, timeout=2) as r:
                if _json.loads(r.read()).get("running"):
                    parts.append("↑ saving")
        except Exception:
            pass

        await update.message.reply_text(" · ".join(parts))
    except Exception:
        await update.message.reply_text("Couldn't reach your Lattice store. Try again in a moment.")


async def _handle_sources(update, context) -> None:
    if not _is_allowed(update):
        return
    sources = context.chat_data.get("last_sources")
    if not sources:
        await update.message.reply_text("No recent sources — ask a question first.")
        return
    lines = []
    for s in sources:
        line = f"[{s['num']}] {s['preview']}"
        meta = " · ".join(p for p in [s["channel"], s["age"]] if p)
        if meta:
            line += f"\n     {meta}"
        lines.append(line)
    await update.message.reply_text("Sources:\n" + "\n".join(lines))


async def _handle_document(update, context) -> None:
    """Handle PDF (and .txt/.md) document uploads."""
    if not _is_allowed(update):
        return
    doc = update.message.document
    if not doc:
        await update.message.reply_text("I can only handle text and PDF files for now.")
        return

    fname = doc.file_name or "upload"
    suffix = ("." + fname.rsplit(".", 1)[-1].lower()) if "." in fname else ""

    await update.message.reply_text("Got it — reading the file now…")

    import tempfile, os
    try:
        tg_file = await doc.get_file()
        with tempfile.NamedTemporaryFile(suffix=suffix or ".bin", delete=False) as tmp:
            await tg_file.download_to_drive(tmp.name)
            tmp_path = tmp.name
    except Exception:
        log.exception("telegram: failed to download document")
        await update.message.reply_text("Couldn't download the file. Try again in a moment.")
        return

    try:
        from lattice.util import extract_file_text
        try:
            text, source_id = extract_file_text(tmp_path)
            # Restore original filename in source_id
            source_id = source_id.replace(os.path.basename(tmp_path), fname) if fname != "upload" else source_id
        except ImportError as exc:
            await update.message.reply_text(str(exc))
            return
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
    finally:
        os.unlink(tmp_path)

    chat_id = update.effective_chat.id
    try:
        from lattice.client import DaemonClient
        result = DaemonClient().ingest_full(text, source_id=source_id)
        added   = result.get("atoms_new", 0)
        updated = result.get("atoms_updated", 0)
        s = lambda n: "s" if n != 1 else ""
        if added == 0 and updated == 0:
            await update.message.reply_text(f"Already knew all of this — {fname} is fully up to date. Nothing new.")
        elif added and updated:
            await update.message.reply_text(f"{fname} absorbed ✓ — {added} new idea{s(added)} picked up, {updated} refreshed with newer info.")
        elif added:
            await update.message.reply_text(f"{fname} absorbed ✓ — {added} new idea{s(added)} saved to your memory.")
        else:
            await update.message.reply_text(f"{fname} absorbed ✓ — {updated} thing{s(updated)} refreshed with newer info.")
    except (RuntimeError, OSError):
        _inbox_fallback(text, chat_id)
        await update.message.reply_text(f"{fname} received. Lattice is offline — I'll process it when it's back. 📥")


async def _handle_reset(update, context) -> None:
    """Clear today's journey — same as the web UI 'Clear' button."""
    if not _is_allowed(update):
        return
    import json as _json
    import urllib.request as _ur
    port = os.environ.get("LATTICE_WEB_PORT", "7337")
    try:
        req = _ur.Request(
            f"http://127.0.0.1:{port}/api/chat/clear-today",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with _ur.urlopen(req, timeout=5) as r:
            data = _json.loads(r.read())
        context.chat_data["qa_history"] = []
        context.chat_data["history"] = []
        await update.message.reply_text("Today's journey cleared. Fresh start.")
    except Exception:
        await update.message.reply_text("Couldn't reach Lattice. Is the daemon running?")


async def _handle_journey(update, context) -> None:
    """Show today's topic journey as a text tree (all channels)."""
    if not _is_allowed(update):
        return
    turns = _get_today_turns(channel=None)  # all channels — one continuous journey
    tree = _build_journey_text(turns)
    if not tree:
        await update.message.reply_text("No journey yet today. Ask something with /ask to start exploring.")
        return
    await update.message.reply_text(f"Today's journey:\n\n{tree}")


async def _handle_non_text(update, context) -> None:
    if not _is_allowed(update):
        return
    await update.message.reply_text("I can only handle text and PDF files. Send a .pdf, .txt, or .md and I'll save it.")


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
    app.add_handler(CommandHandler("sources", _handle_sources))
    app.add_handler(CommandHandler("journey", _handle_journey))
    app.add_handler(CommandHandler("reset", _handle_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, _handle_document))
    app.add_handler(MessageHandler(~filters.TEXT & ~filters.Document.ALL, _handle_non_text))

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
