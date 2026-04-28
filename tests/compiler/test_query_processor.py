"""Unit tests for query_processor.process_query."""

import pytest

from backend.compiler.query_processor import HYPOTHESES_K, process_query


def _valid_response(hypotheses=None, canonical=None, kinds=None) -> str:
    hyps = hypotheses or [
        "Revenue grew 20% in Q2 2025 compared to prior year.",
        "Q2 2025 revenue reached record highs driven by enterprise deals.",
        "The sales team exceeded Q2 targets by a significant margin.",
    ]
    hyps_json = "[" + ", ".join(f'"{h}"' for h in hyps) + "]"
    canonical_json = (
        f'{{"subject": "{canonical["subject"]}", "period": "{canonical["period"]}"}}'
        if canonical
        else "null"
    )
    kinds_list = kinds or ["metric"]
    kinds_json = "[" + ", ".join(f'"{k}"' for k in kinds_list) + "]"
    return f'{{"kinds": {kinds_json}, "hypotheses": {hyps_json}, "canonical": {canonical_json}}}'


@pytest.mark.asyncio
async def test_happy_path_returns_hypotheses_list(mock_chat):
    mock_chat.return_value = _valid_response()
    result = await process_query("What was Q2 revenue growth?")
    assert isinstance(result.hypotheses, list)
    assert len(result.hypotheses) == 3
    assert all(len(h.split()) >= 3 for h in result.hypotheses)


@pytest.mark.asyncio
async def test_happy_path_with_canonical(mock_chat):
    mock_chat.return_value = _valid_response(canonical={"subject": "revenue", "period": "Q2 2025"})
    result = await process_query("What was Q2 revenue growth?")
    assert result.canonical is not None
    assert result.canonical["subject"] == "revenue"
    assert result.canonical["period"] == "Q2 2025"


@pytest.mark.asyncio
async def test_happy_path_no_canonical(mock_chat):
    mock_chat.return_value = _valid_response()
    result = await process_query("Who is on the leadership team?")
    assert result.canonical is None


@pytest.mark.asyncio
async def test_no_kind_field_in_result(mock_chat):
    mock_chat.return_value = _valid_response()
    result = await process_query("some query")
    assert not hasattr(result, "kind")


@pytest.mark.asyncio
async def test_fallback_on_llm_exception(mock_chat):
    mock_chat.side_effect = RuntimeError("LLM unavailable")
    raw = "What is the headcount?"
    result = await process_query(raw)
    assert result.hypotheses == [raw]
    assert result.canonical is None


@pytest.mark.asyncio
async def test_fallback_on_invalid_json(mock_chat):
    mock_chat.return_value = "not json at all"
    raw = "What is the headcount?"
    result = await process_query(raw)
    assert result.hypotheses == [raw]


@pytest.mark.asyncio
async def test_fallback_filters_short_hypotheses(mock_chat):
    # All hypotheses are < 3 words → falls back to raw query
    mock_chat.return_value = '{"hypotheses": ["ok", "yes"], "canonical": null}'
    raw = "What is headcount?"
    result = await process_query(raw)
    assert result.hypotheses == [raw]


@pytest.mark.asyncio
async def test_partial_short_hypotheses_filtered(mock_chat):
    # Mix of valid and too-short — only long ones kept
    mock_chat.return_value = (
        '{"hypotheses": ["ok", "Revenue grew 20% in Q2 2025.", "Pipeline conversion improved in Q2."], '
        '"canonical": null}'
    )
    result = await process_query("Q2 performance?")
    assert len(result.hypotheses) == 2
    assert all(len(h.split()) >= 3 for h in result.hypotheses)


@pytest.mark.asyncio
async def test_calls_chat_exactly_once(mock_chat):
    mock_chat.return_value = _valid_response()
    await process_query("Some query")
    assert mock_chat.call_count == 1


@pytest.mark.asyncio
async def test_passes_response_format(mock_chat):
    mock_chat.return_value = _valid_response()
    await process_query("Some query")
    _, kwargs = mock_chat.call_args
    assert "response_format" in kwargs
