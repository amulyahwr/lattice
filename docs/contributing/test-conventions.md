# Test Conventions

## Running tests

```bash
uv run pytest                              # all tests
uv run pytest tests/test_db.py             # single file
uv run pytest -k test_supersession_links   # single test
```

## LLM mocking

All tests mock LLM calls via `unittest.mock.patch`. Never make real LLM calls in tests.

**Ingest tests** — patch at `lattice.ingest.complete`:

```python
from unittest.mock import patch

with patch("lattice.ingest.complete") as mock_complete:
    mock_complete.side_effect = [
        '{"atoms": [{"kind": "fact", "subject": "test", "content": "A fact."}]}',
        '{"superseded_atom_ids": []}',
    ]
    result = ingest("A fact.", cfg)
```

Every atom requires two LLM responses: (1) the extraction JSON, (2) the supersession reply. Supersession reply format: `'{"superseded_atom_ids": []}'` or `'{"superseded_atom_ids": ["<id>"]}'`.

**Conversation tests** (`classify_intent`, `reformulate_capture`) — patch at `lattice.conversation.complete`:

```python
with patch("lattice.conversation.complete") as mock_complete:
    mock_complete.return_value = "recall"
    result = classify_intent("what do I like?", cfg)
```

**Synthesis tests** — patch `lattice.synthesis.make_llm_client` (returns a mock OpenAI client):

```python
from unittest.mock import MagicMock, patch

mock_client = MagicMock()
mock_client.chat.completions.create.return_value = ...
with patch("lattice.synthesis.make_llm_client", return_value=mock_client):
    result = synthesize(atoms, "question", cfg)
```

**Claude model paths** — patch `lattice.llm._anthropic_complete` for Anthropic SDK dispatch.

## Config in tests

Use `Config(lattice_dir=tmp_path)` directly — no `monkeypatch.setenv` needed:

```python
def test_something(tmp_path):
    cfg = Config(
        lattice_dir=tmp_path,
        llm_provider="ollama",
        llm_model="test-model"
    )
    db = LatticeDB(cfg)
    ...
```

## Fixtures

- `tmp_path` — pytest built-in; provides a fresh temp directory per test
- Use function-level isolation — don't share `LatticeDB` instances between tests

## What not to test

- Don't test LLM output quality — mock the LLM, test the pipeline around it
- Don't test that `complete()` retries on 429 — that's tested in `test_llm.py`
- Don't write tests that require real filesystem paths outside `tmp_path`
