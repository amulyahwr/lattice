import json
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from lattice.config import Config
from lattice.db import LatticeDB
from lattice.selection import select
from lattice.synthesis import stream_synthesis

app = FastAPI(title="Lattice")


class QueryRequest(BaseModel):
    question: str


@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lattice</title>
<style>
  body { font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 0 16px; }
  h1 { margin-bottom: 24px; }
  #query-form { display: flex; gap: 8px; margin-bottom: 24px; }
  #question { flex: 1; padding: 8px 12px; font-size: 1rem; border: 1px solid #ccc; border-radius: 4px; }
  #submit { padding: 8px 16px; font-size: 1rem; cursor: pointer; }
  #answer-section { display: none; }
  #answer { background: #f9f9f9; border-left: 4px solid #555; padding: 12px 16px; margin-bottom: 16px; white-space: pre-wrap; }
  #atoms-section h3 { margin-bottom: 8px; }
  #atoms-list { list-style: none; padding: 0; }
  #atoms-list li { padding: 6px 0; border-bottom: 1px solid #eee; font-size: 0.9rem; color: #444; }
  #loading { color: #888; display: none; }
  #error { color: #c00; display: none; }
  .citation { color: #0057b7; cursor: help; border-bottom: 1px dotted #0057b7; font-size: 0.85em; }
</style>
</head>
<body>
<h1>Lattice</h1>
<form id="query-form">
  <input id="question" type="text" placeholder="Ask a question..." autocomplete="off" />
  <button id="submit" type="submit">Ask</button>
</form>
<div id="loading">Thinking...</div>
<div id="error"></div>
<div id="answer-section">
  <div id="answer"></div>
  <div id="atoms-section">
    <h3>Atoms</h3>
    <ul id="atoms-list"></ul>
  </div>
</div>
<script>
var atomsById = {};

function renderCitations(text) {
  // Replace [label][src:id] with a tooltip span, or bare [src:id] with a span.
  // Escapes HTML in text content first to prevent XSS.
  function escHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  return escHtml(text).replace(
    /\\[([^\\]]+)\\]\\[src:([^\\]]+)\\]|\\[src:([^\\]]+)\\]/g,
    function(_, label, id1, id2) {
      var id = id1 || id2;
      var lbl = label || id;
      var atom = atomsById[id];
      var title = atom ? (atom.source_title || atom.subject || id) : id;
      return '<span class="citation" title="' + escHtml(title) + '" data-src="' + escHtml(id) + '">[' + escHtml(lbl) + ']</span>';
    }
  );
}

document.getElementById('query-form').addEventListener('submit', async function(e) {
  e.preventDefault();
  const question = document.getElementById('question').value.trim();
  if (!question) return;

  const answerEl = document.getElementById('answer');
  const listEl = document.getElementById('atoms-list');
  answerEl.textContent = '';
  listEl.innerHTML = '';
  document.getElementById('loading').style.display = 'block';
  document.getElementById('error').style.display = 'none';
  document.getElementById('answer-section').style.display = 'none';

  try {
    const resp = await fetch('/api/query', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question})
    });
    if (!resp.ok) throw new Error('Request failed: ' + resp.status);

    document.getElementById('answer-section').style.display = 'block';
    // Keep loading visible until first token — select+synthesis take 10-20s

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += decoder.decode(value, {stream: true});
      const parts = buf.split('\\n\\n');
      buf = parts.pop();
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith('data: ')) continue;
        const evt = JSON.parse(line.slice(6));
        if (evt.type === 'token') {
          document.getElementById('loading').style.display = 'none';
          answerEl.textContent += evt.text;
        } else if (evt.type === 'atoms') {
          atomsById = {};
          listEl.innerHTML = '';
          (evt.atoms || []).forEach(function(atom) {
            if (atom.source_id) atomsById[atom.source_id] = atom;
            const li = document.createElement('li');
            li.textContent = (atom.subject || '(no subject)') + ' — ' + (atom.kind || '');
            listEl.appendChild(li);
          });
        } else if (evt.type === 'citations_applied') {
          answerEl.innerHTML = renderCitations(evt.answer);
        } else if (evt.type === 'error') {
          document.getElementById('loading').style.display = 'none';
          document.getElementById('error').textContent = evt.message;
          document.getElementById('error').style.display = 'block';
        }
      }
    }
  } catch (err) {
    document.getElementById('error').textContent = err.message;
    document.getElementById('error').style.display = 'block';
    document.getElementById('loading').style.display = 'none';
  }
});
</script>
</body>
</html>"""


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/api/query")
async def api_query(req: QueryRequest) -> StreamingResponse:
    db = LatticeDB(Config.from_env().lattice_dir)

    def _generate():
        # Run select() here so response headers go out immediately,
        # keeping the event loop unblocked.
        atoms = select(req.question, db=db)
        yield f'data: {json.dumps({"type": "atoms", "atoms": atoms})}\n\n'
        yield from stream_synthesis(req.question, atoms)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/atoms/recent")
async def api_atoms_recent(limit: int = 20):
    db = LatticeDB(Config.from_env().lattice_dir)
    atoms = [a for a in db.all() if not a.is_superseded]
    # sort by observed_at descending, nulls last
    atoms.sort(
        key=lambda a: a.observed_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    atoms = atoms[:limit]
    return [
        {
            "atom_id": a.atom_id,
            "subject": a.subject,
            "kind": a.kind,
            "observed_at": a.observed_at.isoformat() if a.observed_at else None,
            "source_id": a.source_id,
        }
        for a in atoms
    ]
