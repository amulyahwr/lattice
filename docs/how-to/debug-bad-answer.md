# Debug a Bad Answer

When Lattice returns an unhelpful or incorrect answer, the issue is usually in selection (wrong atoms retrieved) or synthesis (model confabulated). This guide walks through how to diagnose which.

## Step 1: Check what atoms were returned

The web UI shows source chips below every answer. Click each chip to see the atom's content and metadata. If the atoms look irrelevant, the problem is in **selection**. If the atoms look correct but the answer doesn't match them, the problem is in **synthesis**.

## Step 2: Use the feedback buttons

Click 👎 on a bad answer. If specific atom chips were wrong sources, click the ✕ on those chips to dismiss them. This feeds the quality score update loop — dismissed atoms score lower in future recalls.

## Step 3: Check the query reformulation

If you asked a follow-up question, Lattice may have reformulated it. The web UI shows the reformulated query in small text below your question. If reformulation distorted your intent, this is the likely culprit.

To disable reformulation for a query, start a fresh conversation (clear button) rather than following up.

## Step 4: Check the selection directly

Use the `lattice_select` MCP tool (or `POST /api/query` with a debug client) to inspect the raw atom pack:

```bash
curl -s -X POST http://localhost:7337/api/answer \
  -H "Content-Type: application/json" \
  -d '{"question": "your question here", "conversation_history": []}' \
  | python3 -m json.tool
```

Look at the `atoms` array — are the right atoms present?

## Step 5: Check for supersession issues

If you recently updated a fact, the old atom may be showing up. Check:

```bash
grep -r "subject: <your subject>" ~/.lattice/*.md
```

Any atom with `is_superseded: true` should not appear in answers. If it does, run:

```bash
uv run lattice graph rebuild
```

## Step 6: Enable tracing

```bash
export LATTICE_TRACE=true
uv run lattice-daemon
```

Re-run the query. Check `~/.lattice/traces.jsonl` for the trace of that query — it shows BM25 seed count, dense seed count, BFS expansion count, final atom count, and synthesis latency.

## Step 7: Check dense search

If you have `LATTICE_DENSE_SEEDS=1`, the dense index might be surfacing irrelevant atoms. Try disabling it temporarily:

```bash
LATTICE_DENSE_SEEDS=0 uv run lattice-daemon
```

If the answer improves, the dense model may be finding spurious vocabulary matches.

## Common patterns

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Answer says "I don't have information" but you definitely captured it | BM25 vocabulary mismatch | Enable `LATTICE_DENSE_SEEDS=1` |
| Answer is about the wrong topic | Reformulation distorted the query | Clear conversation history and ask directly |
| Answer cites old superseded facts | Supersession didn't run properly | `lattice graph rebuild` |
| Answer is correct but doesn't cite the most relevant atoms | Quality scores not calibrated yet | Give 👍 feedback on good answers |
| Synthesis confabulates details not in atoms | Model is hallucinating | Use a larger/better synthesis model (`SYNTHESIS_MODEL`) |
