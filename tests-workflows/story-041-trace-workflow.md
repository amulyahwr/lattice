# STORY-041 — End-to-End Query Trace Test Workflow

Verifies that `LATTICE_TRACE=true` writes a structured `traces.jsonl` record per query,
that query text is never stored (SHA-1 hash only), that `GET /api/trace/{trace_id}` returns
the matching record, and that `LATTICE_TRACE=false` (default) produces zero overhead.

---

## Pre-flight

```bash
uv run lattice-daemon status   # confirm {"ok": true}
grep '^version' pyproject.toml # confirm 0.9.0
```

---

## Phase 1 — Unit tests (automated)

```bash
uv run pytest tests/test_story_041.py -v
```

Expected: **16 passed**. Covers:
- `QueryTrace.create()` hashes query, sets channel
- `set_reformulated()` sets `reformulated_hash`
- Dataclass defaults (empty lists, False flags, zero stage_ms)
- `TraceWriter.write()` → `TraceWriter.read()` round-trip
- `read()` returns `None` for unknown or missing file
- Multiple writes → correct record returned per `trace_id`, two lines in file
- `select()` with `trace` arg → `bm25_seeds` and `final_atoms` populated
- `select()` with `trace=None` → no crash (default path)
- `stream_synthesis()` with `trace` arg → `cited_atoms` set, `no_answer=False`
- `stream_synthesis()` with `<<NO_INFO>>` → `no_answer=True`
- `Config.lattice_trace` defaults to `False`
- `LATTICE_TRACE=true` env var → `cfg.lattice_trace=True`
- `GET /api/trace/{id}` with tracing off → 404
- `GET /api/trace/{id}` with tracing on, unknown id → 404
- `GET /api/trace/{id}` with pre-written record → 200 + correct data

---

## Phase 2 — Config env var (automated)

```bash
python3 -c "
import os; os.environ.update({'LATTICE_TRACE': 'true', 'LATTICE_DIR': '/tmp', 'LLM_PROVIDER': 'ollama', 'LLM_MODEL': 'test'})
from lattice.config import Config
cfg = Config.from_env()
assert cfg.lattice_trace is True, f'Expected True, got {cfg.lattice_trace}'
print('PASS — LATTICE_TRACE=true parsed correctly')
"

python3 -c "
import os; os.environ.update({'LATTICE_TRACE': 'false', 'LATTICE_DIR': '/tmp', 'LLM_PROVIDER': 'ollama', 'LLM_MODEL': 'test'})
from lattice.config import Config
cfg = Config.from_env()
assert cfg.lattice_trace is False
print('PASS — LATTICE_TRACE=false (default) correct')
"
```

---

## Phase 3 — traces.jsonl not created when LATTICE_TRACE=false (automated)

```bash
python3 -c "
import tempfile, pathlib
from lattice.config import Config
from lattice.db import LatticeDB
from lattice.selection import select
from lattice.models import Atom
from datetime import datetime, timezone

with tempfile.TemporaryDirectory() as tmp:
    p = pathlib.Path(tmp)
    cfg = Config(lattice_dir=p, llm_provider='ollama', llm_model='test', lattice_trace=False)
    db = LatticeDB(p)
    atom = Atom(atom_id='test-001', subject='Postgres', kind='fact',
                content='Postgres is fast', source='user',
                ingested_at=datetime.now(timezone.utc),
                observed_at=datetime.now(timezone.utc))
    db.write(atom)
    select('tell me about Postgres', db=db, cfg=cfg, trace=None)
    traces = p / 'traces.jsonl'
    assert not traces.exists(), f'traces.jsonl should not exist when tracing off'
    print('PASS — traces.jsonl not created when LATTICE_TRACE=false')
"
```

---

## Phase 4 — trace fields populated correctly (automated)

```bash
python3 -c "
import tempfile, pathlib, json
from lattice.config import Config
from lattice.db import LatticeDB
from lattice.selection import select
from lattice.trace import QueryTrace, TraceWriter
from lattice.models import Atom
from datetime import datetime, timezone

with tempfile.TemporaryDirectory() as tmp:
    p = pathlib.Path(tmp)
    cfg = Config(lattice_dir=p, llm_provider='ollama', llm_model='test', lattice_trace=True)
    db = LatticeDB(p)
    for i in range(3):
        atom = Atom(atom_id=f'atom-{i:03}', subject='Postgres', kind='fact',
                    content=f'Postgres fact {i}', source='user',
                    ingested_at=datetime.now(timezone.utc),
                    observed_at=datetime.now(timezone.utc))
        db.write(atom)

    trace = QueryTrace.create('tell me about Postgres', channel='web')
    select('tell me about Postgres', db=db, cfg=cfg, trace=trace)

    # Write and read back
    writer = TraceWriter(cfg)
    writer.write(trace)
    record = writer.read(trace.trace_id)

    assert record is not None
    assert len(record['bm25_seeds']) > 0, 'bm25_seeds empty'
    assert all('atom_id' in s and 'score' in s for s in record['bm25_seeds']), 'seed missing fields'
    assert len(record['final_atoms']) > 0, 'final_atoms empty'
    assert record['query_hash'] != 'tell me about Postgres', 'query text leaked into hash field'
    assert len(record['query_hash']) == 16, f'hash should be 16 chars, got {len(record[\"query_hash\"])}'
    assert record['channel'] == 'web'
    assert record['no_answer'] is False
    print(f'PASS — bm25_seeds={len(record[\"bm25_seeds\"])}, final_atoms={len(record[\"final_atoms\"])}, hash={record[\"query_hash\"]}')
"
```

---

## Phase 5 — query text never appears in traces.jsonl (automated)

```bash
python3 -c "
import tempfile, pathlib
from lattice.config import Config
from lattice.trace import QueryTrace, TraceWriter

SENSITIVE = 'my secret password is hunter2'

with tempfile.TemporaryDirectory() as tmp:
    p = pathlib.Path(tmp)
    cfg = Config(lattice_dir=p, llm_provider='ollama', llm_model='test')
    trace = QueryTrace.create(SENSITIVE)
    trace.final_atoms = ['abc123']
    TraceWriter(cfg).write(trace)
    content = (p / 'traces.jsonl').read_text()
    assert SENSITIVE not in content, 'FAIL: query text found in traces.jsonl!'
    assert 'hunter2' not in content, 'FAIL: query text found in traces.jsonl!'
    print('PASS — query text not present in traces.jsonl')
    print(f'  hash stored: {trace.query_hash}')
"
```

---

## Phase 6 — multiple queries append, not overwrite (automated)

```bash
python3 -c "
import tempfile, pathlib, json
from lattice.config import Config
from lattice.trace import QueryTrace, TraceWriter

with tempfile.TemporaryDirectory() as tmp:
    p = pathlib.Path(tmp)
    cfg = Config(lattice_dir=p, llm_provider='ollama', llm_model='test')
    writer = TraceWriter(cfg)
    ids = []
    for q in ['query one', 'query two', 'query three']:
        t = QueryTrace.create(q)
        writer.write(t)
        ids.append(t.trace_id)
    lines = (p / 'traces.jsonl').read_text().strip().splitlines()
    assert len(lines) == 3, f'Expected 3 lines, got {len(lines)}'
    for tid in ids:
        assert writer.read(tid) is not None, f'Could not read {tid}'
    print(f'PASS — {len(lines)} trace lines, all readable by trace_id')
"
```

---

## Phase 7 — API endpoint returns correct record (automated)

```bash
python3 -c "
import tempfile, pathlib
from fastapi.testclient import TestClient
from lattice.config import Config
from lattice.db import LatticeDB
from lattice.trace import QueryTrace, TraceWriter
import lattice.web.app as _web

with tempfile.TemporaryDirectory() as tmp:
    p = pathlib.Path(tmp)
    cfg = Config(lattice_dir=p, llm_provider='ollama', llm_model='test', lattice_trace=True)
    db = LatticeDB(p)
    _web.set_config(cfg, db)

    trace = QueryTrace.create('what is my coffee preference?')
    trace.final_atoms = ['atom-abc']
    trace.stage_ms = {'selection': 55, 'reformulation': 0, 'synthesis': 1200}
    TraceWriter(cfg).write(trace)

    client = TestClient(_web.app)
    resp = client.get(f'/api/trace/{trace.trace_id}')
    assert resp.status_code == 200, f'Expected 200, got {resp.status_code}'
    data = resp.json()
    assert data['trace_id'] == trace.trace_id
    assert data['final_atoms'] == ['atom-abc']
    assert data['stage_ms']['selection'] == 55
    assert 'coffee' not in str(data), 'query text leaked into trace response'
    print(f'PASS — GET /api/trace/{trace.trace_id[:8]}... returned correct record')
    print(f'  stage_ms: {data[\"stage_ms\"]}')
"
```

---

## Phase 8 — API returns 404 when tracing disabled (automated)

```bash
python3 -c "
import tempfile
from fastapi.testclient import TestClient
from lattice.config import Config
from lattice.db import LatticeDB
import lattice.web.app as _web

with tempfile.TemporaryDirectory() as tmp:
    import pathlib; p = pathlib.Path(tmp)
    cfg = Config(lattice_dir=p, llm_provider='ollama', llm_model='test', lattice_trace=False)
    db = LatticeDB(p)
    _web.set_config(cfg, db)
    client = TestClient(_web.app)
    resp = client.get('/api/trace/any-id')
    assert resp.status_code == 404
    print('PASS — 404 when LATTICE_TRACE=false')
"
```

---

## Phase 9 — End-to-end via daemon (you do this)

Enable tracing and restart the daemon:

```bash
# Add to your env (or .env file)
export LATTICE_TRACE=true

uv run lattice-daemon   # restart with LATTICE_TRACE=true
uv run lattice-daemon status
```

Open the web UI and ask a question:

```
http://localhost:7337
```

Query: `what do I know about Postgres?`

Then check `traces.jsonl`:

```bash
tail -1 ~/.lattice/traces.jsonl | python3 -m json.tool
```

**Expected record shape:**
```json
{
  "trace_id": "<uuid>",
  "ts": "2026-...",
  "query_hash": "<16 hex chars>",
  "channel": "web",
  "reformulated_hash": null,
  "bm25_seeds": [{"atom_id": "...", "score": 0.83}, ...],
  "dense_hits": [],
  "bfs_expanded": ["...", "..."],
  "final_atoms": ["...", "..."],
  "cited_atoms": ["..."],
  "stage_ms": {"selection": 120, "reformulation": 0, "synthesis": 1400},
  "no_answer": false,
  "pii_protected": false
}
```

**Verify query text is absent:**
```bash
# Should print nothing (query text not stored)
grep -i "postgres" ~/.lattice/traces.jsonl && echo "FAIL: text leaked" || echo "PASS: no query text in file"
```

**Retrieve by trace_id:**
```bash
TRACE_ID=$(tail -1 ~/.lattice/traces.jsonl | python3 -c "import sys,json; print(json.load(sys.stdin)['trace_id'])")
curl -s http://localhost:7337/api/trace/$TRACE_ID | python3 -m json.tool
```

Expected: same record as in the file.

---

## Phase 10 — trace_id present in SSE atoms event (you do this)

Open browser devtools (Network tab) → Filter by `query` → fire a question.

In the SSE stream, find the `atoms` event. It should contain `"trace_id"`:

```json
{"type": "atoms", "atoms": [...], "context_reset": false, "trace_id": "<uuid>"}
```

This `trace_id` is what a future debug panel (`?debug=1`, STORY-043) will use to fetch the trace.

---

## Phase 11 — LATTICE_TRACE=false: zero overhead (you do this)

```bash
# No LATTICE_TRACE in env (default)
uv run lattice-daemon status
```

Ask a question. Then verify:

```bash
ls ~/.lattice/traces.jsonl 2>/dev/null && echo "FAIL: file created when tracing off" || echo "PASS: no traces.jsonl"
```

Expected: file does not exist.

---

## Pass criteria

| Check | Phase | How | Pass if |
|-------|-------|-----|---------|
| 16 unit tests pass | 1 | `pytest` | All green |
| `LATTICE_TRACE=true` env var parsed | 2 | automated script | `cfg.lattice_trace=True` |
| `traces.jsonl` not created when off | 3 | automated script | File absent |
| `bm25_seeds` + `final_atoms` populated | 4 | automated script | Non-empty lists, correct fields |
| Query text never in file | 5 | automated script | No raw text, 16-char hash present |
| Multiple queries append not overwrite | 6 | automated script | 3 lines, all readable |
| `GET /api/trace/{id}` returns record | 7 | automated script | 200, correct fields |
| `GET /api/trace/{id}` off → 404 | 8 | automated script | 404 |
| End-to-end trace record shape | 9 | you | All fields present, no text |
| `trace_id` in SSE atoms event | 10 | you | Field present in browser devtools |
| No file when `LATTICE_TRACE=false` | 11 | you | `traces.jsonl` absent |
