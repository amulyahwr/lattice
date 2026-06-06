"""Tests for STORY-018 (Telegram bot), STORY-024 (/ask recall), STORY-025 (/save session),
inbox drain (_drain_inbox), intent classifier (_classify), _notify_telegram."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lattice.telegram_bot import _classify, _inbox_fallback


# ---------------------------------------------------------------------------
# Intent classifier — _classify
# ---------------------------------------------------------------------------

class TestClassify:
    # --- recall signals ---
    def test_question_mark_is_recall(self):
        assert _classify("what do I prefer for coffee?") == "recall"

    def test_question_word_what(self):
        assert _classify("What is my gym routine") == "recall"

    def test_question_word_how(self):
        assert _classify("how often do I go to the gym") == "recall"

    def test_question_word_when(self):
        assert _classify("when did I buy the car") == "recall"

    def test_question_word_remind(self):
        assert _classify("remind me about the project deadline") == "recall"

    def test_question_word_show(self):
        assert _classify("show me what I know about coffee") == "recall"

    def test_recall_phrase_remind_me(self):
        assert _classify("can you remind me what do I prefer") == "recall"

    def test_recall_phrase_tell_me_about(self):
        assert _classify("tell me about my travel plans") == "recall"

    def test_recall_phrase_what_do_i(self):
        assert _classify("what do I usually have for breakfast") == "recall"

    def test_recall_phrase_have_i(self):
        assert _classify("have I been to Japan before") == "recall"

    # --- capture signals ---
    def test_i_prefix_is_capture(self):
        assert _classify("I prefer dark coffee") == "capture"

    def test_i_decided(self):
        assert _classify("I decided to use Postgres") == "capture"

    def test_i_bought(self):
        assert _classify("I bought a new bike today") == "capture"

    def test_just_prefix(self):
        assert _classify("just finished the meeting") == "capture"

    def test_decided_prefix(self):
        assert _classify("decided to postpone the launch") == "capture"

    def test_note_prefix(self):
        assert _classify("note: remember to call Alex") == "capture"

    def test_fyi_prefix(self):
        assert _classify("fyi: the build is broken") == "capture"

    # --- ambiguous / unclear ---
    def test_single_word_is_unclear(self):
        assert _classify("coffee") == "unclear"

    def test_topic_phrase_is_unclear(self):
        assert _classify("the gym") == "unclear"

    def test_uncertain_statement_is_unclear(self):
        assert _classify("not sure about this") == "unclear"

    def test_empty_string_is_unclear(self):
        assert _classify("") == "unclear"

    def test_whitespace_only_is_unclear(self):
        assert _classify("   ") == "unclear"

    # --- case insensitivity ---
    def test_uppercase_question_word(self):
        assert _classify("WHAT is my preference") == "recall"

    def test_uppercase_capture(self):
        assert _classify("I PREFER dark mode") == "capture"

    def test_mixed_case_phrase(self):
        assert _classify("Remind Me about the trip") == "recall"


# ---------------------------------------------------------------------------
# Inbox fallback — writes telegram-{chat_id}-{uuid}.txt
# ---------------------------------------------------------------------------

class TestInboxFallback:
    def test_creates_file_in_inbox(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        monkeypatch.setenv("LATTICE_INBOX", str(tmp_path / "inbox"))
        _inbox_fallback("test message", chat_id=12345)
        files = list((tmp_path / "inbox").glob("telegram-12345-*.txt"))
        assert len(files) == 1
        assert files[0].read_text() == "test message"

    def test_filename_encodes_chat_id(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        monkeypatch.setenv("LATTICE_INBOX", str(tmp_path / "inbox"))
        _inbox_fallback("hello", chat_id=99999)
        files = list((tmp_path / "inbox").glob("*.txt"))
        assert files[0].name.startswith("telegram-99999-")

    def test_creates_inbox_dir_if_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        inbox = tmp_path / "inbox"
        monkeypatch.setenv("LATTICE_INBOX", str(inbox))
        assert not inbox.exists()
        _inbox_fallback("test", chat_id=1)
        assert inbox.exists()

    def test_multiple_calls_create_separate_files(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        monkeypatch.setenv("LATTICE_INBOX", str(tmp_path / "inbox"))
        _inbox_fallback("msg1", chat_id=111)
        _inbox_fallback("msg2", chat_id=111)
        files = list((tmp_path / "inbox").glob("telegram-111-*.txt"))
        assert len(files) == 2

    def test_file_content_preserved_exactly(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        monkeypatch.setenv("LATTICE_INBOX", str(tmp_path / "inbox"))
        text = "I prefer café au lait ☕ every morning"
        _inbox_fallback(text, chat_id=1)
        files = list((tmp_path / "inbox").glob("*.txt"))
        assert files[0].read_text(encoding="utf-8") == text


# ---------------------------------------------------------------------------
# Inbox drain — _drain_inbox
# ---------------------------------------------------------------------------

class TestDrainInbox:
    def test_drain_processes_existing_txt(self, tmp_path):
        from lattice.daemon import InboxEventHandler, _drain_inbox
        from lattice.db import LatticeDB

        inbox = tmp_path / "inbox"
        inbox.mkdir()
        processed = tmp_path / "processed"
        processed.mkdir()
        db = LatticeDB(tmp_path / "lattice")
        f = inbox / "note.txt"
        f.write_text("pre-existing note")

        handler = InboxEventHandler(db=db, processed_dir=processed)
        extraction = '{"atoms": [{"subject": "note", "source": "document", "content": "pre-existing note.", "kind": "fact", "valid_from": null, "valid_until": null}]}'
        supersession = '{"superseded_atom_id": null}'

        with patch("lattice.ingest.complete", side_effect=[extraction, supersession]):
            _drain_inbox(handler, MagicMock(inbox_dir=inbox, processed_dir=processed))

        assert not f.exists()
        assert (processed / "note.txt").exists()

    def test_drain_empty_inbox_is_noop(self, tmp_path):
        from lattice.daemon import InboxEventHandler, _drain_inbox
        from lattice.db import LatticeDB

        inbox = tmp_path / "inbox"
        inbox.mkdir()
        processed = tmp_path / "processed"
        processed.mkdir()
        db = LatticeDB(tmp_path / "lattice")
        handler = InboxEventHandler(db=db, processed_dir=processed)
        _drain_inbox(handler, MagicMock(inbox_dir=inbox, processed_dir=processed))
        assert list(inbox.iterdir()) == []

    def test_drain_moves_binary_files_to_processed(self, tmp_path):
        """Binary files are attempted, rejected, then moved to processed."""
        from lattice.daemon import InboxEventHandler, _drain_inbox
        from lattice.db import LatticeDB

        inbox = tmp_path / "inbox"
        inbox.mkdir()
        processed = tmp_path / "processed"
        processed.mkdir()
        db = LatticeDB(tmp_path / "lattice")
        png = inbox / "image.png"
        png.write_bytes(bytes(range(256)) * 10)  # clearly binary

        handler = InboxEventHandler(db=db, processed_dir=processed)
        _drain_inbox(handler, MagicMock(inbox_dir=inbox, processed_dir=processed))
        assert not png.exists() or (processed / "image.png").exists()

    def test_drain_processes_multiple_files(self, tmp_path):
        from lattice.daemon import InboxEventHandler, _drain_inbox
        from lattice.db import LatticeDB

        inbox = tmp_path / "inbox"
        inbox.mkdir()
        processed = tmp_path / "processed"
        processed.mkdir()
        db = LatticeDB(tmp_path / "lattice")
        (inbox / "a.txt").write_text("note a")
        (inbox / "b.txt").write_text("note b")

        extraction = '{"atoms": [{"subject": "note", "source": "document", "content": "note.", "kind": "fact", "valid_from": null, "valid_until": null}]}'
        supersession = '{"superseded_atom_id": null}'

        handler = InboxEventHandler(db=db, processed_dir=processed)
        with patch("lattice.ingest.complete", side_effect=[extraction, supersession, extraction, supersession]):
            _drain_inbox(handler, MagicMock(inbox_dir=inbox, processed_dir=processed))

        assert not (inbox / "a.txt").exists()
        assert not (inbox / "b.txt").exists()


# ---------------------------------------------------------------------------
# _notify_telegram — daemon sends follow-up reply after drain
# ---------------------------------------------------------------------------

class TestNotifyTelegram:
    def test_no_token_is_noop(self, monkeypatch):
        from lattice.daemon import _notify_telegram
        monkeypatch.delenv("LATTICE_TELEGRAM_TOKEN", raising=False)
        # Should not raise
        _notify_telegram("telegram-123-abc.txt", atom_count=2)

    def test_non_telegram_filename_is_noop(self, monkeypatch):
        from lattice.daemon import _notify_telegram
        monkeypatch.setenv("LATTICE_TELEGRAM_TOKEN", "token123")
        with patch("urllib.request.urlopen") as mock_open:
            _notify_telegram("inbox-drop.txt", atom_count=2)
            mock_open.assert_not_called()

    def test_malformed_filename_no_crash(self, monkeypatch):
        from lattice.daemon import _notify_telegram
        monkeypatch.setenv("LATTICE_TELEGRAM_TOKEN", "token123")
        # filename starts with telegram- but no valid chat_id
        _notify_telegram("telegram-notanumber-abc.txt", atom_count=1)

    def test_sends_request_on_valid_filename(self, monkeypatch):
        from lattice.daemon import _notify_telegram
        monkeypatch.setenv("LATTICE_TELEGRAM_TOKEN", "mytoken")
        with patch("urllib.request.urlopen") as mock_open:
            _notify_telegram("telegram-12345-abcdef.txt", atom_count=3)
            mock_open.assert_called_once()

    def test_network_error_does_not_raise(self, monkeypatch):
        from lattice.daemon import _notify_telegram
        monkeypatch.setenv("LATTICE_TELEGRAM_TOKEN", "mytoken")
        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            _notify_telegram("telegram-12345-abc.txt", atom_count=1)  # must not raise


# ---------------------------------------------------------------------------
# Telegram message handlers (async, mocked update/context)
# ---------------------------------------------------------------------------

def _make_update(text: str, chat_id: int = 123, user_id: int = 42):
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


import asyncio


def run(coro):
    return asyncio.run(coro)


class TestHandleMessage:
    # --- positive ---
    def test_capture_intent_ingests(self):
        from lattice.telegram_bot import _handle_message
        update = _make_update("I prefer dark coffee")
        ctx = _make_context()
        with patch("lattice.client.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest.return_value = ["a1"]
            run(_handle_message(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "Saved" in reply

    def test_capture_adds_to_history(self):
        from lattice.telegram_bot import _handle_message
        update = _make_update("I prefer dark coffee")
        ctx = _make_context()
        with patch("lattice.client.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest.return_value = ["a1"]
            run(_handle_message(update, ctx))
        assert any(h["text"] == "I prefer dark coffee" for h in ctx.chat_data.get("history", []))

    def test_recall_intent_calls_synthesize(self):
        from lattice.telegram_bot import _handle_message
        update = _make_update("what do I prefer for coffee?")
        ctx = _make_context()
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true, "answer": "You prefer dark coffee.", "atom_count": 1}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            run(_handle_message(update, ctx))
        update.message.reply_text.assert_called()

    def test_recall_adds_to_history(self):
        from lattice.telegram_bot import _handle_message
        update = _make_update("what do I prefer for coffee?")
        ctx = _make_context()
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true, "answer": "You prefer dark coffee.", "atom_count": 1}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            run(_handle_message(update, ctx))
        history = ctx.chat_data.get("history", [])
        roles = [h["role"] for h in history]
        assert "user" in roles
        assert "assistant" in roles

    def test_unclear_intent_asks_clarification(self):
        from lattice.telegram_bot import _handle_message
        update = _make_update("coffee")
        ctx = _make_context()
        run(_handle_message(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "save" in reply.lower() or "ask" in reply.lower()
        assert ctx.chat_data.get("pending_text") == "coffee"

    def test_save_reply_to_clarification(self):
        from lattice.telegram_bot import _handle_message
        ctx = _make_context({"pending_text": "coffee thoughts"})
        update = _make_update("save")
        with patch("lattice.client.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.return_value = {"atoms_new": 1, "atoms_updated": 0, "atom_ids": ["a1"]}
            run(_handle_message(update, ctx))
        assert "pending_text" not in ctx.chat_data
        reply = update.message.reply_text.call_args[0][0]
        assert "Saved" in reply

    def test_ask_reply_to_clarification(self):
        from lattice.telegram_bot import _handle_message
        ctx = _make_context({"pending_text": "coffee"})
        update = _make_update("ask")
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true, "answer": "You prefer dark coffee.", "atom_count": 1}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            run(_handle_message(update, ctx))
        assert "pending_text" not in ctx.chat_data

    # --- negative / edge ---
    def test_daemon_down_writes_inbox(self, tmp_path, monkeypatch):
        from lattice.telegram_bot import _handle_message
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        monkeypatch.setenv("LATTICE_INBOX", str(tmp_path / "inbox"))
        update = _make_update("I prefer dark coffee", chat_id=555)
        ctx = _make_context()
        with patch("lattice.client.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.side_effect = OSError("no socket")
            run(_handle_message(update, ctx))
        files = list((tmp_path / "inbox").glob("telegram-555-*.txt"))
        assert len(files) == 1
        reply = update.message.reply_text.call_args[0][0]
        assert "offline" in reply.lower()

    def test_unknown_user_silently_dropped(self, monkeypatch):
        from lattice.telegram_bot import _handle_message
        monkeypatch.setenv("LATTICE_TELEGRAM_ALLOWED_IDS", "99999")
        update = _make_update("I prefer dark coffee", user_id=12345)
        ctx = _make_context()
        run(_handle_message(update, ctx))
        update.message.reply_text.assert_not_called()

    def test_empty_message_ignored(self):
        from lattice.telegram_bot import _handle_message
        update = _make_update("")
        ctx = _make_context()
        with patch("lattice.client.DaemonClient") as mock_cls:
            run(_handle_message(update, ctx))
            mock_cls.return_value.ingest_full.assert_not_called()
        update.message.reply_text.assert_not_called()

    def test_new_message_drops_stale_pending(self):
        """If user sends a new message while clarification pending, pending is dropped."""
        from lattice.telegram_bot import _handle_message
        ctx = _make_context({"pending_text": "old unclear thing"})
        update = _make_update("I bought a new bike")  # clear capture
        with patch("lattice.client.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.return_value = {"atoms_new": 1, "atoms_updated": 0, "atom_ids": ["a1"]}
            run(_handle_message(update, ctx))
        assert "pending_text" not in ctx.chat_data

    def test_zero_atoms_returns_already_known_message(self):
        from lattice.telegram_bot import _handle_message
        update = _make_update("I prefer dark coffee")
        ctx = _make_context()
        with patch("lattice.client.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.return_value = {"atoms_new": 0, "atoms_updated": 0, "atom_ids": []}
            run(_handle_message(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "already" in reply.lower() or "nothing new" in reply.lower()

    def test_recall_no_atoms_found(self):
        from lattice.telegram_bot import _handle_message
        update = _make_update("what do I prefer for tea?")
        ctx = _make_context()
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true, "answer": null, "atom_count": 0}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            run(_handle_message(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "nothing" in reply.lower() or "yet" in reply.lower()

    def test_long_answer_split_into_chunks(self):
        from lattice.telegram_bot import _handle_message
        update = _make_update("what do I know?")
        ctx = _make_context()
        long_answer = "x" * 9000
        mock_resp = MagicMock()
        mock_resp.read.return_value = f'{{"ok": true, "answer": "{long_answer}", "atom_count": 1}}'.encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            run(_handle_message(update, ctx))
        assert update.message.reply_text.call_count >= 2


class TestHandleSave:
    # --- positive ---
    def test_save_ingests_history_and_clears(self):
        from lattice.telegram_bot import _handle_save
        ctx = _make_context({"history": [
            {"role": "user", "text": "I prefer dark coffee"},
            {"role": "user", "text": "what is my coffee preference?"},
            {"role": "assistant", "text": "You prefer dark coffee."},
        ]})
        update = _make_update("/save")
        with patch("lattice.client.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.return_value = {"atoms_new": 2, "atoms_updated": 0, "atom_ids": ["a1", "a2"]}
            run(_handle_save(update, ctx))
        assert ctx.chat_data["history"] == []
        reply = update.message.reply_text.call_args[0][0]
        assert "saved" in reply.lower()

    def test_save_formats_as_conversation_chunk(self):
        from lattice.telegram_bot import _handle_save
        ctx = _make_context({"history": [
            {"role": "user", "text": "hello"},
            {"role": "assistant", "text": "world"},
        ]})
        update = _make_update("/save")
        with patch("lattice.client.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.return_value = {"atoms_new": 0, "atoms_updated": 0, "atom_ids": []}
            run(_handle_save(update, ctx))
        ingested_text = mock_cls.return_value.ingest_full.call_args[0][0]
        assert "user: hello" in ingested_text
        assert "assistant: world" in ingested_text

    def test_save_uses_telegram_source_id(self):
        from lattice.telegram_bot import _handle_save
        ctx = _make_context({"history": [{"role": "user", "text": "test"}]})
        update = _make_update("/save")
        with patch("lattice.client.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.return_value = {"atoms_new": 0, "atoms_updated": 0, "atom_ids": []}
            run(_handle_save(update, ctx))
        call_args = mock_cls.return_value.ingest_full.call_args
        assert "telegram" in str(call_args)

    # --- negative / edge ---
    def test_save_empty_session(self):
        from lattice.telegram_bot import _handle_save
        update = _make_update("/save")
        ctx = _make_context()
        run(_handle_save(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "nothing" in reply.lower()

    def test_save_daemon_down(self):
        from lattice.telegram_bot import _handle_save
        ctx = _make_context({"history": [{"role": "user", "text": "test"}]})
        update = _make_update("/save")
        with patch("lattice.client.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.side_effect = OSError("no socket")
            run(_handle_save(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "offline" in reply.lower()

    def test_save_zero_new_atoms(self):
        """All content already known — still clears history."""
        from lattice.telegram_bot import _handle_save
        ctx = _make_context({"history": [{"role": "user", "text": "I prefer dark coffee"}]})
        update = _make_update("/save")
        with patch("lattice.client.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.return_value = {"atoms_new": 0, "atoms_updated": 0, "atom_ids": []}
            run(_handle_save(update, ctx))
        assert ctx.chat_data["history"] == []
        reply = update.message.reply_text.call_args[0][0]
        assert "saved" in reply.lower() or "nothing new" in reply.lower()
