"""Tests for STORY-027 — Telegram recall feedback."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lattice.telegram_bot import _match_reason, _post_feedback

import asyncio


def run(coro):
    return asyncio.run(coro)


def _make_update(text: str, user_id: int = 42, chat_id: int = 123):
    update = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.effective_user.id = user_id
    update.effective_chat.id = chat_id
    return update


def _make_context(chat_data: dict | None = None):
    ctx = MagicMock()
    ctx.chat_data = chat_data or {}
    ctx.args = []
    return ctx


# ---------------------------------------------------------------------------
# _match_reason
# ---------------------------------------------------------------------------

class TestMatchReason:
    # --- positive ---
    def test_wrong_sources(self):
        assert _match_reason("wrong sources") == "wrong_sources"

    def test_wrong_source_singular(self):
        assert _match_reason("wrong source") == "wrong_sources"

    def test_inaccurate(self):
        assert _match_reason("inaccurate") == "inaccurate"

    def test_incorrect(self):
        assert _match_reason("incorrect") == "inaccurate"

    def test_incomplete(self):
        assert _match_reason("incomplete") == "incomplete"

    def test_missing(self):
        assert _match_reason("missing info") == "incomplete"

    def test_off_topic(self):
        assert _match_reason("off topic") == "off_topic"

    def test_irrelevant(self):
        assert _match_reason("irrelevant") == "off_topic"

    def test_case_insensitive(self):
        assert _match_reason("INACCURATE") == "inaccurate"

    # --- negative ---
    def test_unknown_reason_returns_none(self):
        assert _match_reason("dunno") is None

    def test_empty_returns_none(self):
        assert _match_reason("") is None

    # --- edge ---
    def test_partial_match_in_sentence(self):
        assert _match_reason("this was completely inaccurate") == "inaccurate"


# ---------------------------------------------------------------------------
# _post_feedback — sends to /api/feedback
# ---------------------------------------------------------------------------

class TestPostFeedback:
    def test_posts_to_feedback_endpoint(self):
        with patch("urllib.request.urlopen") as mock_open:
            _post_feedback("what is X?", "X is Y.", "up")
            mock_open.assert_called_once()

    def test_includes_rating(self):
        import json
        captured = []
        def capture(req, timeout=None):
            captured.append(json.loads(req.data))
            return MagicMock().__enter__.return_value
        with patch("urllib.request.urlopen", side_effect=capture):
            _post_feedback("what is X?", "X is Y.", "up")
        assert captured[0]["rating"] == "up"

    def test_includes_reason_when_provided(self):
        import json
        captured = []
        def capture(req, timeout=None):
            captured.append(json.loads(req.data))
            return MagicMock().__enter__.return_value
        with patch("urllib.request.urlopen", side_effect=capture):
            _post_feedback("what is X?", "X is Y.", "down", "inaccurate")
        assert captured[0]["reason"] == "inaccurate"

    def test_network_error_does_not_raise(self):
        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            _post_feedback("q", "a", "up")  # must not raise


# ---------------------------------------------------------------------------
# Feedback flow in _handle_message
# ---------------------------------------------------------------------------

class TestFeedbackFlow:
    # --- positive (thumbs up) ---
    def test_thumbs_up_emoji_records_feedback(self):
        from lattice.telegram_bot import _handle_message
        ctx = _make_context({"pending_feedback": {"question": "what is X?", "answer": "X is Y."}})
        update = _make_update("👍")
        with patch("lattice.telegram_bot._post_feedback") as mock_fb:
            run(_handle_message(update, ctx))
        mock_fb.assert_called_once_with("what is X?", "X is Y.", "up")

    def test_thumbs_up_clears_pending(self):
        from lattice.telegram_bot import _handle_message
        ctx = _make_context({"pending_feedback": {"question": "q", "answer": "a"}})
        update = _make_update("👍")
        with patch("lattice.telegram_bot._post_feedback"):
            run(_handle_message(update, ctx))
        assert "pending_feedback" not in ctx.chat_data

    def test_yes_word_triggers_thumbs_up(self):
        from lattice.telegram_bot import _handle_message
        ctx = _make_context({"pending_feedback": {"question": "q", "answer": "a"}})
        update = _make_update("yes")
        with patch("lattice.telegram_bot._post_feedback") as mock_fb:
            run(_handle_message(update, ctx))
        mock_fb.assert_called_with("q", "a", "up")

    def test_thumbs_up_replies_thanks(self):
        from lattice.telegram_bot import _handle_message
        ctx = _make_context({"pending_feedback": {"question": "q", "answer": "a"}})
        update = _make_update("👍")
        with patch("lattice.telegram_bot._post_feedback"):
            run(_handle_message(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "thanks" in reply.lower() or "👍" in reply

    # --- positive (thumbs down + reason) ---
    def test_thumbs_down_asks_for_reason(self):
        from lattice.telegram_bot import _handle_message
        ctx = _make_context({"pending_feedback": {"question": "q", "answer": "a"}})
        update = _make_update("👎")
        run(_handle_message(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "wrong" in reply.lower() or "inaccurate" in reply.lower()

    def test_thumbs_down_sets_rating_in_pending(self):
        from lattice.telegram_bot import _handle_message
        ctx = _make_context({"pending_feedback": {"question": "q", "answer": "a"}})
        update = _make_update("👎")
        run(_handle_message(update, ctx))
        assert ctx.chat_data["pending_feedback"]["rating"] == "down"

    def test_reason_reply_records_feedback(self):
        from lattice.telegram_bot import _handle_message
        ctx = _make_context({"pending_feedback": {"question": "q", "answer": "a", "rating": "down"}})
        update = _make_update("inaccurate")
        with patch("lattice.telegram_bot._post_feedback") as mock_fb:
            run(_handle_message(update, ctx))
        mock_fb.assert_called_once_with("q", "a", "down", "inaccurate")

    def test_reason_reply_clears_pending(self):
        from lattice.telegram_bot import _handle_message
        ctx = _make_context({"pending_feedback": {"question": "q", "answer": "a", "rating": "down"}})
        update = _make_update("inaccurate")
        with patch("lattice.telegram_bot._post_feedback"):
            run(_handle_message(update, ctx))
        assert "pending_feedback" not in ctx.chat_data

    def test_unknown_reason_still_records_with_none(self):
        from lattice.telegram_bot import _handle_message
        ctx = _make_context({"pending_feedback": {"question": "q", "answer": "a", "rating": "down"}})
        update = _make_update("dunno")
        with patch("lattice.telegram_bot._post_feedback") as mock_fb:
            run(_handle_message(update, ctx))
        mock_fb.assert_called_once_with("q", "a", "down", None)

    # --- negative / edge ---
    def test_non_feedback_reply_drops_pending_and_processes_normally(self):
        from lattice.telegram_bot import _handle_message
        ctx = _make_context({"pending_feedback": {"question": "q", "answer": "a"}})
        update = _make_update("I bought a new bike")
        with patch("lattice.telegram_bot._post_feedback") as mock_fb:
            with patch("lattice.client.DaemonClient") as mock_dc:
                mock_dc.return_value.ingest.return_value = ["a1"]
                run(_handle_message(update, ctx))
        mock_fb.assert_not_called()
        assert "pending_feedback" not in ctx.chat_data

    def test_recall_sets_pending_feedback(self):
        from lattice.telegram_bot import _handle_message
        update = _make_update("what do I prefer?")
        ctx = _make_context()
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true, "answer": "You prefer dark coffee.", "atom_count": 1}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            run(_handle_message(update, ctx))
        assert "pending_feedback" in ctx.chat_data
        assert ctx.chat_data["pending_feedback"]["question"] == "what do I prefer?"

    def test_recall_prompts_for_feedback(self):
        from lattice.telegram_bot import _handle_message
        update = _make_update("what do I prefer?")
        ctx = _make_context()
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true, "answer": "You prefer dark coffee.", "atom_count": 1}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            run(_handle_message(update, ctx))
        last_reply = update.message.reply_text.call_args_list[-1][0][0]
        assert "👍" in last_reply or "👎" in last_reply

    def test_no_feedback_prompt_when_many_atoms(self):
        """High atom_count = confident answer — skip feedback prompt."""
        from lattice.telegram_bot import _handle_message
        update = _make_update("what do I prefer?")
        ctx = _make_context()
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true, "answer": "You prefer dark coffee.", "atom_count": 5}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            run(_handle_message(update, ctx))
        assert "pending_feedback" not in ctx.chat_data
        # only one reply — the answer itself, no feedback prompt
        assert update.message.reply_text.call_count == 1

    def test_feedback_prompt_at_atom_count_1(self):
        """Boundary: atom_count=1 should still prompt."""
        from lattice.telegram_bot import _handle_message
        update = _make_update("what do I prefer?")
        ctx = _make_context()
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true, "answer": "You prefer dark coffee.", "atom_count": 1}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            run(_handle_message(update, ctx))
        assert "pending_feedback" in ctx.chat_data

    def test_no_feedback_prompt_at_atom_count_2(self):
        """Boundary: atom_count=2 should NOT prompt — confident enough."""
        from lattice.telegram_bot import _handle_message
        update = _make_update("what do I prefer?")
        ctx = _make_context()
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true, "answer": "You prefer dark coffee.", "atom_count": 2}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            run(_handle_message(update, ctx))
        assert "pending_feedback" not in ctx.chat_data
