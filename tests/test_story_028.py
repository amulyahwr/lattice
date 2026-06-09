"""Tests for STORY-028 — Synthesis "no answer" post-processing."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from lattice.config import Config
from lattice.synthesis import (
    _NO_ANSWER_PHRASE,
    _NO_ANSWER_SENTINEL,
    _is_no_answer,
    synthesize,
    stream_synthesis,
)

_CFG = Config(llm_provider="ollama", llm_model="test-model")


_ATOMS = [{"atom_id": "a1", "subject": "coffee", "kind": "preference", "content": "Prefers dark roast.", "observed_at": "2025-01-01"}]


# ---------------------------------------------------------------------------
# _is_no_answer — detection
# ---------------------------------------------------------------------------

class TestIsNoAnswer:
    # --- positive: phrases that should trigger replacement ---
    def test_cannot_determine(self):
        assert _is_no_answer("I cannot determine this from the atoms.")

    def test_cant_determine(self):
        assert _is_no_answer("I can't determine the answer.")

    def test_not_mentioned(self):
        assert _is_no_answer("This topic is not mentioned in the atoms.")

    def test_no_information_about(self):
        assert _is_no_answer("There is no information about skiing in the atoms.")

    def test_atoms_do_not(self):
        assert _is_no_answer("The atoms do not contain relevant information.")

    def test_do_not_contain(self):
        assert _is_no_answer("The provided atoms do not contain anything about this.")

    def test_doesnt_contain(self):
        assert _is_no_answer("The lattice doesn't contain this fact.")

    def test_there_is_no(self):
        assert _is_no_answer("There is no stored fact about hiking preferences.")

    def test_there_are_no(self):
        assert _is_no_answer("There are no atoms related to this topic.")

    def test_no_record(self):
        assert _is_no_answer("There is no record of this in memory.")

    def test_nothing_in_the(self):
        assert _is_no_answer("Nothing in the provided context answers this.")

    def test_not_stored(self):
        assert _is_no_answer("This preference is not stored in the lattice.")

    def test_not_in_the_lattice(self):
        assert _is_no_answer("That detail is not in the lattice.")

    def test_no_relevant(self):
        assert _is_no_answer("No relevant atoms found for this query.")

    def test_not_available(self):
        assert _is_no_answer("That information is not available in my memory.")

    def test_case_insensitive(self):
        assert _is_no_answer("I CANNOT DETERMINE this.")

    def test_phrase_in_longer_paragraph(self):
        assert _is_no_answer(
            "Based on the atoms provided, I cannot determine what your skiing preference is. "
            "The atoms contain information about coffee and books."
        )

    # --- negative: genuine answers should NOT trigger ---
    def test_relevant_answer_not_flagged(self):
        assert not _is_no_answer("You prefer dark roast coffee.")

    def test_partial_answer_not_flagged(self):
        assert not _is_no_answer("You prefer dark coffee, though no brand is recorded.")

    def test_empty_string_not_flagged(self):
        assert not _is_no_answer("")

    def test_short_answer_not_flagged(self):
        assert not _is_no_answer("Dark roast.")

    def test_already_replaced_phrase_not_reflagged(self):
        # The replacement phrase itself must not re-trigger
        assert not _is_no_answer(_NO_ANSWER_PHRASE)

    # --- edge ---
    def test_partial_word_doesnt_trigger(self):
        # "container" contains "contain" — make sure we don't false-positive
        # The regex uses word-boundary-like patterns so "container" should not match "do not contain"
        assert not _is_no_answer("Use a sealed container for storage.")

    def test_multiline_input(self):
        assert _is_no_answer("Line one.\nI cannot determine the answer.\nLine three.")

    def test_sentinel_triggers_replacement(self):
        assert _is_no_answer("<<NO_INFO>>")

    def test_sentinel_embedded_in_text(self):
        assert _is_no_answer("Some preamble <<NO_INFO>> trailing")

    def test_sentinel_constant_matches(self):
        assert _is_no_answer(_NO_ANSWER_SENTINEL)


# ---------------------------------------------------------------------------
# synthesize() — non-streaming path
# ---------------------------------------------------------------------------

class TestSynthesizeNoAnswer:
    def _mock_client(self, answer_text: str) -> MagicMock:
        mock_client = MagicMock()
        completion = MagicMock()
        completion.choices[0].message.content = answer_text
        completion.choices[0].message.tool_calls = None
        mock_client.chat.completions.create.return_value = completion
        return mock_client

    def test_verbose_no_answer_replaced(self):
        with patch("lattice.synthesis.make_llm_client", return_value=self._mock_client(
            "I cannot determine your skiing preference from the provided atoms."
        )):
            with patch("lattice.synthesis.resolve_model", return_value="test-model"):
                result = synthesize("what's my skiing preference?", _ATOMS, _CFG)
        assert result.answer == _NO_ANSWER_PHRASE

    def test_genuine_answer_preserved(self):
        with patch("lattice.synthesis.make_llm_client", return_value=self._mock_client(
            "You prefer dark roast coffee."
        )):
            with patch("lattice.synthesis.resolve_model", return_value="test-model"):
                result = synthesize("what coffee do I like?", _ATOMS, _CFG)
        assert result.answer == "You prefer dark roast coffee."

    def test_no_atoms_returns_not_found(self):
        result = synthesize("anything", [], _CFG)
        assert "No relevant information" in result.answer

    def test_raw_response_preserved_even_when_replaced(self):
        """raw_response always holds the LLM's actual output for debugging."""
        llm_text = "I cannot determine this from the atoms."
        with patch("lattice.synthesis.make_llm_client", return_value=self._mock_client(llm_text)):
            with patch("lattice.synthesis.resolve_model", return_value="test-model"):
                result = synthesize("q", _ATOMS, _CFG)
        assert result.answer == _NO_ANSWER_PHRASE
        assert result.raw_response == llm_text

    def test_partial_answer_with_gap_not_replaced(self):
        """A real partial answer mentioning a gap should not be clobbered."""
        with patch("lattice.synthesis.make_llm_client", return_value=self._mock_client(
            "You prefer dark coffee, but your tea preference is not recorded."
        )):
            with patch("lattice.synthesis.resolve_model", return_value="test-model"):
                result = synthesize("what do I drink?", _ATOMS, _CFG)
        assert "dark coffee" in result.answer


# ---------------------------------------------------------------------------
# stream_synthesis() — streaming path
# ---------------------------------------------------------------------------

class TestStreamSynthesisNoAnswer:
    def _mock_stream_client(self, chunks: list[str]) -> MagicMock:
        """Build a mock OpenAI client that streams the given text chunks."""
        mock_client = MagicMock()

        # Tool-loop call: no tool calls
        tool_resp = MagicMock()
        tool_resp.choices[0].message.tool_calls = None
        tool_resp.choices[0].message.content = ""

        # Streaming chunks
        stream_chunks = []
        for text in chunks:
            chunk = MagicMock()
            chunk.choices[0].delta.content = text
            stream_chunks.append(chunk)

        mock_client.chat.completions.create.side_effect = [tool_resp, iter(stream_chunks)]
        return mock_client

    def _collect_events(self, gen) -> list[dict]:
        events = []
        for line in gen:
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        return events

    def test_verbose_no_answer_replaced_in_citations_applied(self):
        with patch("lattice.synthesis.make_llm_client", return_value=self._mock_stream_client(
            ["I cannot determine", " your skiing preference."]
        )):
            with patch("lattice.synthesis.resolve_model", return_value="test-model"):
                events = self._collect_events(stream_synthesis("q", _ATOMS, _CFG))
        ca = next(e for e in events if e["type"] == "citations_applied")
        assert ca["answer"] == _NO_ANSWER_PHRASE

    def test_genuine_answer_preserved_in_stream(self):
        with patch("lattice.synthesis.make_llm_client", return_value=self._mock_stream_client(
            ["You prefer ", "dark roast coffee."]
        )):
            with patch("lattice.synthesis.resolve_model", return_value="test-model"):
                events = self._collect_events(stream_synthesis("q", _ATOMS, _CFG))
        ca = next(e for e in events if e["type"] == "citations_applied")
        assert "dark roast" in ca["answer"]

    def test_stream_no_atoms_yields_not_found(self):
        events = self._collect_events(stream_synthesis("anything", [], _CFG))
        token_texts = [e["text"] for e in events if e["type"] == "token"]
        assert any("No relevant" in t for t in token_texts)

    def test_done_event_always_emitted(self):
        with patch("lattice.synthesis.make_llm_client", return_value=self._mock_stream_client(
            ["I cannot determine this."]
        )):
            with patch("lattice.synthesis.resolve_model", return_value="test-model"):
                events = self._collect_events(stream_synthesis("q", _ATOMS, _CFG))
        assert any(e["type"] == "done" for e in events)

    def test_token_events_still_emitted_before_replacement(self):
        """Tokens stream before the citations_applied replacement — both should exist."""
        with patch("lattice.synthesis.make_llm_client", return_value=self._mock_stream_client(
            ["I cannot determine this."]
        )):
            with patch("lattice.synthesis.resolve_model", return_value="test-model"):
                events = self._collect_events(stream_synthesis("q", _ATOMS, _CFG))
        assert any(e["type"] == "token" for e in events)
        assert any(e["type"] == "citations_applied" for e in events)
