# lattice Product Priorities

Goal: build a local-first MCP server for persistent, inspectable knowledge that works well with coding assistants and local models. LongMemEval is an evaluation yardstick, not the product target.

Product constraints:

- Local-only: no hosted service, no required daemon, no external database.
- Works with API models and Ollama; expensive enrichment must be optional.
- Atom files remain human-readable and git-trackable.
- Ingest can handle many local sources, but useful partial memory should commit quickly.
- Selection should be fast, graph-aware, and should not wait for active ingest or background enrichment.

## Active Roadmap

Current atom set: **p27** (`gpt-4o-mini` ingest via OpenRouter, 3192 atoms, ~31.9/session, 100 sessions). **Canonical baseline: p27b — 68%** (p27 atoms + current code, `_is_no_answer()` active). p27 (76%) is a stale comparison — it was run before `_is_no_answer()` was added to synthesis; 8pp gap is code drift not a regression. Canonical lattice dirs: `results/p27/openaigpt4omini_longmemeval_oracle_inference.lattices`. Current code: `sandbox` branch.

p27b results (clean baseline at 68%): single-session-user 78.6%, single-session-preference 50%, single-session-assistant 90.9%, multi-session 51.9%, temporal 69.2%, knowledge-update 75%. **Remaining gaps: multi-session (51.9%) and single-session-preference (50%).**

**M11 shipped** (time decay per kind, `selection.py`). LongMemEval-oracle cannot measure it — all questions use `as_of` anchor → atom age ≈ 0 → decay ≈ 1.0. Validated on **LongMemEval-S knowledge-update subset** (34 questions, 550-640 atoms each, 90-304 day date spreads — cap binding): baseline 61.8% → M11 **73.5% (+11.8pp)**. Env: `LATTICE_TIME_DECAY=0` to disable.

**p31 (BFS decay sort) — reverted.** Sorted BFS-expanded atoms by decay factor after `bfs_expand()`. Retrieval metrics unchanged (precision −0.7pp, atom_mrr 0.985→0.571). Accuracy gain (+5.9pp) was synthesis noise at n=34 — atom ordering identical for all 3 flipped questions. Reverted.

**p32 — S-version stratified baseline (30/category, n=176 after 4 ingest errors removed).** First cross-category measurement. Ingest errors: 4 large-haystack questions (44–53 sessions) hit LLM output limits — accepted, 2.2% loss. Retrieval: BM25 hit=94.4% recall=0.913 atom_precision=0.307; Selected barely changes (BFS adds almost nothing at this scale). **Category accuracy:**

| Category | Accuracy | n | SE |
|---|---|---|---|
| single-session-preference | **33.3%** | 30 | ±9.1% |
| temporal-reasoning | **51.7%** | 29 | ±9.3% |
| multi-session | 63.0% | 27 | ±9.6% |
| knowledge-update | 70.0% | 30 | ±9.1% |
| single-session-user | 76.7% | 30 | ±9.1% |
| single-session-assistant | **83.3%** | 30 | ±9.1% |
| **Overall** | **63.1%** | 176 | ±3.6% |

Failure mass concentrated in preference (33%) and temporal (52%). Together = 53% of failures. Multi-session (63%) is better than expected — BFS helps here. Oracle dataset (68%) overstated performance on preference/temporal; S-version is the correct benchmark going forward.

**p33 (synthesis prompt, n=176, reverted).** Clarified `valid_from` vs `observed_at` semantics, added ordering instruction, strengthened preference grounding. All deltas within SE (±9.1% per category, ±3.8% overall). No signal — reverted.

**p34 — M5 dense seed augmentation (n=180, `LATTICE_DENSE_SEEDS=1`).** Reused p32 lattice dirs. On first `preload()`, embed index built from all atoms via `_rebuild_embed_index()` (BAAI/bge-small-en-v1.5, 384-dim). Dense top-10 hits merged with BM25 seeds before BFS. **Category accuracy:**

| Category | p32 (baseline) | p34 (dense) | delta | retrieval hit Δ |
|---|---|---|---|---|
| single-session-preference | 33.3% | **50.0%** | **+16.7pp** | +16.6pp |
| temporal-reasoning | 51.7% | 46.7% | −5.0pp (noise) | +3.6pp |
| multi-session | 63.0% | 66.7% | +3.7pp | 0pp |
| knowledge-update | 70.0% | 70.0% | 0.0pp | 0pp |
| single-session-user | 76.7% | **83.3%** | **+6.6pp** | +3.7pp |
| single-session-assistant | 83.3% | **90.0%** | **+6.7pp** | 0pp |
| **Overall** | **63.1%** (n=176) | **67.8%** (n=180) | **+4.7pp** | |

Preference +16.7pp is 1.8×SE — driven directly by retrieval (Hit 76.7%→93.3%). Vocab-mismatch atoms ("gym"↔"workout") now found. Temporal −5.0pp is noise (n difference: 4 ingest-error questions now scored 0 in p34). **Shipped.** `LATTICE_DENSE_SEEDS=1`, optional dep `fastembed` (semantic group). Sidecar: `LATTICE_DIR/graph/embed_matrix.npy` + `embed_ids.json`.

**Shipped.** Next: temporal reasoning gap (46.7%) — retrieval now fine (100% hit), failures are synthesis. M12 (reinforcement counting) or temporal date anchoring at ingest.

**p35 — relative time annotation on `observed_at` (n=180, reverted).** Added "N days ago" annotation to each atom's `observed_at` in the synthesis context block, computed relative to `query_date`. Hypothesis: synthesis would anchor `date_diff` calls on pre-computed relative offsets rather than raw ISO dates. **Overall: 66.7% (−1.1pp). Preference: 50.0% (0pp). Multi-session: −10pp.** Relative annotations introduced cross-session temporal confusion — synthesis treated "12 days ago" labels from different sessions as if they shared a common reference frame. No temporal gain. **Reverted.**

**p36 — dense-rerank pack trim (n=180, reverted).** After BFS, trimmed synthesis pack to top-15 atoms for PREFERENCE queries and top-20 for TEMPORAL, re-ranked by dense cosine similarity. Also expanded `_RECOMMENDATION_PHRASES` in `query.py` to catch more advisory queries. **Overall: 67.2% (−0.6pp vs p34). Preference: 50.0% (0pp).** Root cause surfaced: relevant preference atoms are `kind=fact/event/goal`, not `kind=preference` — dense trim cut the wrong atoms. Phrase expansion misclassified multi-session and knowledge-update queries as RECOMMENDATION → single-session-user −6.7pp, single-session-assistant −6.7pp. **Reverted.**

**p37 — kind-first ordering (n=180, reverted).** For PREFERENCE queries, floated `kind ∈ {preference, belief, recommendation}` atoms to the front of the synthesis pack before sending to LLM. Hypothesis: synthesis uses atoms in order — front-loaded preference atoms get prioritized. **Overall: 64.4% (−3.4pp). Preference: 53.3% (+3.3pp). Multi-session: −6.7pp. Knowledge-update: −6.7pp. Single-session-assistant: −10pp.** Root cause confirmed: atoms floated to front were the wrong preference atoms (from other sessions); atoms demoted were the correct context atoms for non-preference categories. Preference gain is within SE; regressions elsewhere are not. **Reverted.**

**p38 — BFS diversity fix (inconclusive, reverted).** Snapshot BM25 diversity before dense augmentation to prevent dense seeds from inflating the diversity probe. Hypothesis: dense seeds from cross-session atoms were flipping single-session queries from POINTED to EXPANSION. Investigation showed BM25 seeds already have diversity > 1 for preference queries (12-18 sessions) — dense seeds didn't change the decision. Bug does not exist in p34 production code. **Reverted.** No eval run needed.

**p39 — majority-session POINTED probe (n=180, reverted).** Modified diversity probe: if >50% of probe seeds share a single `session_id`, force POINTED mode (max=14 atoms). Hypothesis: single-session questions were being over-expanded; forcing POINTED would cut noise. **Overall: 62.2% (−5.6pp). Preference: 50.0% (0pp). Temporal: −6.7pp. Multi-session: −6.7pp. Single-session-assistant: −6.7pp.** AtomPrecision doubled (0.208→0.421) but accuracy dropped — POINTED mode cuts atoms needed for multi-hop temporal and assistant questions. Majority-session heuristic too aggressive: many legitimate multi-session queries have one dominant session. **Reverted.**

**Root causes established (p35–p39):**
- **Preference (50%)**: retrieval is solved (Hit 93.3%). Relevant atoms are `kind=fact/event/goal` — ingest classifies personal context as facts, not preferences. No retrieval or synthesis fix can reclassify existing atoms. Fix requires ingest-time change: extract preference/goal/belief atoms from personal context statements. Synthesis prompt for preference grounding was tried in p33 → no signal.
- **Temporal (46.7%)**: 13/16 failures use `valid_from` in `date_diff` instead of `observed_at`. 3/16 failures are ordering questions with no tool call. Synthesis prompt approaches blocked: p28 (event-date prompt) → −6pp; p33 (valid_from/observed_at clarification) → no signal. Open path: remove `valid_from` from synthesis context (data change, not prompt) or ingest-time `event_date` field.

**Temporal gap — benchmark artifact, not a product gap.** The 13/16 failures where synthesis uses `valid_from` in `date_diff` instead of `observed_at` are correct product behavior. In real use: if the user says "I attended a baking class on March 20" on March 25, `valid_from=March 20` (event date) is the right anchor for "how many days ago did I attend?" LongMemEval grounds temporal answers on `observed_at` (session timestamp) because synthetic sessions use relative phrasing ("I attended yesterday"). Optimizing for `observed_at` would hurt real users. Do not pursue `valid_from` removal or `observed_at`-forcing prompt changes — they are eval gaming. Temporal 46.7% is accepted as a benchmark artifact. Synthesis prompt approaches already exhausted: p28 (−6pp), p33 (no signal).

**Session-scoped preference pullup — ruled out by data.** Avg pref+goal+belief+constraint atoms in pack: failures=8.5, passes=9.7 — nearly identical. Passes succeed not because they have more preference atoms but because they have the *right* atoms. In 8/14 hit=True failures the top-atom session and top-pref session differ — the pack is fragmented across 12-18 sessions. Adding more preference atoms from sessions already in the pack adds more wrong ones. Not worth pursuing.

**Root cause confirmed: preference failure is an ingest quality problem.** The relevant context for advisory queries ("User grows cherry tomatoes at home," "User had success with the lemon cake") is stored as `kind=fact` with broad subjects ("cooking," "gardening"). BM25 and dense search match generic advisory queries ("dinner suggestions") to all cooking atoms across 12-18 sessions — the specific personal context atom is 1-of-57. No selection or synthesis fix reclassifies existing atoms. Fix is at ingest time.

**Next milestone — M17: Preference-aware ingest.** Two targeted changes to `ingest.py` `_SYSTEM` prompt:

1. **Kind classification for personal context**: Add guidance that personal habits, tendencies, practices, and personal context that would inform a recommendation should use `kind=preference`, not `kind=fact`. Explicit "I prefer/like/hate" → `kind=preference` already works. Implicit personal context ("I grow herbs at home," "I commute by bike," "I've been cooking vegetarian lately") → currently misclassified as `kind=fact`.

2. **Functional subjects for preference atoms**: Preference atoms should use subjects that reflect their advisory role ("dietary preference," "cooking style," "commute habit," "gardening practice") rather than content-specific subjects ("cherry tomatoes," "bike"). This keeps atoms findable by advisory queries ("what does the user prefer about cooking?") while still clustering under a shared topic.

   Example corrections:
   - "User grows cherry tomatoes in the backyard" → `kind=preference`, subject=`"gardening"` or `"cooking ingredients"` ✓ (not `kind=fact`, subject=`"cherry tomatoes"`)
   - "User has been cooking vegetarian meals lately" → `kind=preference`, subject=`"dietary preference"` ✓
   - "User commutes to work by bike daily" → `kind=preference`, subject=`"commute"` ✓

**Eval plan for M17:** Re-ingest 5-10 preference-failing sessions with new prompt, manually inspect extracted atoms (are relevant preference atoms now `kind=preference` with right subjects?), then full re-ingest of all 100 sessions → p40 eval run. Expected: preference category 50% → 65%+ if retrieval can surface the right atoms. Cross-category risk: minimal — only kind classification and subject labeling change for personal context atoms; fact/event/count/recommendation extraction unchanged.

| Priority | File(s) | Product Change | Why It Matters |
| --- | --- | --- | --- |
| ~~P25~~ ✅ | `selection.py` | **Remove 2-stage LLM filter**: `select()` = `_retrieve()`. Ablation winner: **(C) score>0 seeds + BFS rescore → 72%**. A=71%, B=70%, C=72%. C: multi-session 67% (+11pp vs A), 0 LLM calls/query. `LATTICE_SEED_MIN_SCORE=0.001` + `LATTICE_BFS_RESCORE=1` in prod. | Net +1pp vs baseline, 0 LLM overhead. Multi-session recovered. Preference 50% is the remaining gap. |
| ~~P26d~~ ✅ | `selection.py` | **Mode-conditional seed filter**: score>0 filter only in EXPANSION mode; POINTED keeps all probe seeds. **Result: 71% (-1pp vs p26c)**. preference +17pp (67%), temporal +8pp (73%). multi-session -15pp (52%) — pointed mode passing noisy seeds into single-session synthesis floods multi-session BFS. **Reverted — p26c remains prod config.** | Net regression. Multi-session loss outweighs single-session gain. p26c score>0 filter applied globally is the right tradeoff. |
| ~~M9~~ ✅ | `ingest.py`, `synthesis.py` | **Numeric extraction precision**: `kind=count` atom type for aggregate numeric facts ("owns 3 bikes", "attended 5 sessions"). Synthesis prefers `kind=count` atoms over re-enumerating instances. Fresh ingest → 3192 atoms (~31.9/session). **Result: 76% (+4pp vs p26c)**. preference +33pp, knowledge-update +13pp, temporal +4pp. multi-session -4pp, single-session-assistant -9pp. | Counting was 15/28 failures in p26c. `kind=count` is a proper data contract — ingest produces it, synthesis trusts it structurally. |
| ~~P26e~~ ⏭️ | `synthesis.py` | **Temporal duration fix**: attempted prompt patch — explicit event-date endpoints + week/month unit conversion. **p28: 70% (-6pp)**. temporal -12pp, knowledge-update -13pp. Overcorrected: forcing event-date endpoints breaks queries where today is the correct reference. **Reverted.** Root cause is synthesis picking wrong event atom, not a prompt-fixable pattern. | Closed as won't fix via synthesis prompt. Temporal failures are atom selection quality issues. |
| ~~M11~~ ✅ | `selection.py` | **Time decay per kind**: pre-BFS seed weight multiplier — exponential decay by `observed_at` age, half-life per kind (reminder: 3d, event: 60d, decision: 180d, preference/belief: 365d, fact/count: 730d). Decay reference = `as_of` when provided (historical queries), else wall clock. `LATTICE_TIME_DECAY=0` to disable. **Validated on LongMemEval-S KU-wide: +11.8pp (61.8%→73.5%)** on 34 knowledge-update questions with 90-304 day date spreads and 550-640 atoms (cap-binding). Not measurable on oracle subset — `as_of` anchor collapses decay to ≈1.0. | Stale atoms ranked identically to recent ones in BM25 seeding. Decay reorders seeds so fresh atoms fill BFS cap first, pushing stale old-version atoms out. |
| ~~M5~~ ✅ | `embed.py`, `db.py`, `selection.py` | **Dense seed augmentation** (seed stage only): augment BM25 seeds with dense NN hits before BFS. `dense_search()` in `embed.py`. Index built at `write()` time; `_rebuild_embed_index()` bootstraps from existing atoms on `preload()`. `LATTICE_DENSE_SEEDS=1` to enable; `LATTICE_DENSE_TOP_K` (default 10). Optional dep `fastembed` (semantic group). **p34: preference +16.7pp (33.3%→50.0%), overall +4.7pp (63.1%→67.8%).** | Vocab mismatch ("gym" ≠ "workout", "own" ≠ "bikes"). Preference Hit 76.7%→93.3% — 7 previously invisible atoms now surfaced. Only seed augmentation is safe — output reranking confirmed harmful (p16b-replay -23pp temporal). |
| M17 | `ingest.py` | **Preference-aware ingest**: classify personal habits/tendencies/practices as `kind=preference` (not `kind=fact`). Add functional subjects for preference atoms ("dietary preference," "commute habit") so advisory queries find them. Re-ingest required. **p40 eval target: preference 50% → 65%+.** | Personal context stored as `kind=fact` with broad subjects is unreachable by advisory queries. Root cause of all 15 preference failures in p34. Product-beneficial: users want Lattice to know their habits, not just their events. |
| M12 | `db.py`, `ingest.py` | **Reinforcement counting**: bump `recurrence_count` field instead of supersede/dedup when same fact re-ingested. Frequently-confirmed atoms score higher in seed weighting. | Same fact recurring across ingests currently lost to dedup. Recurrence = confidence signal at zero LLM cost. |
| M13 | `ingest.py`, `models.py`, `selection.py` | **Confidence scoring at extraction**: LLM assigns `confidence ∈ [0,1]` per atom at ingest. Stored as atom field. Selection: threshold-based filter at query time. | Moves relevance judgment from query time to ingest time. Zero LLM at query. |
| M6 / P13 | `graph.py`, `db.py`, `ingest.py` | **Semantic relation enrichment** (optional): `updates`, `contradicts`, `supports`, `elaborates`, `temporally_before` edges after graph indexing. Off by default for Ollama. | Deeper BFS paths for multi-session aggregation without blocking local ingest/query. Prerequisite for M7 topic hubs. |
| M7 / P21 | `graph.py`, `selection.py` | **Topic hubs**: hub nodes from connected components; store aliases, member atoms, latest `observed_at`, centroid text. Broad queries → concept cluster → member atoms. Depends on M6. | Multi-session queries land on topic hub before drilling atoms. P21-broad-subjects attempt (-6pp) used wrong edge type (same_subject_as across sessions). Hub nodes are the product-native fix. |
| M16 | `graph.py`, `privacy.py`, `ingest.py` | **Named entity graph nodes** (optional, post-M7): NER at ingest adds `entity:PERSON` and `entity:ORG` nodes to graph; BFS expands from them. NER infrastructure shared with STORY-033 (`EntityRedactor` in `privacy.py`) — build once, reuse here. **Depends on M7** — entity nodes must follow hub design to avoid p21-style over-connection flood. Off by default; `LATTICE_NER_ENRICH=1` to enable. | Selection vocab mismatch for person/org queries ("Shivika's skills" scores 0 on BM25 if atoms say only subjects). Entity nodes enable BFS expansion without touching BM25. Not for ingest attribution — that is handled by the ingest.py `_SYSTEM` named person prompt rule. |
| M4 / P18 | `selection.py`, `server.py` | **Selection debug mode**: BM25 ranks/scores, BFS expansion paths, fallback trigger, include reasons. Surface in web UI alongside answer feedback. | Makes memory behavior explainable. Feeds feedback loop for tuning M11/M12/M13 weights. |
| P20 | `db.py`, `server.py` | **Memory namespaces**: project/workspace isolation via `LATTICE_NAMESPACE`. | Prevents cross-project contamination. Multiple `LATTICE_DIR` dirs is the current workaround. |
| P12 | `ingest.py`, `server.py`, `db.py` | **Ingest job status**: `job_id`, indexed/active/failed source counts, `graph_version`, `last_commit_at`. | Product UX — local users need visibility into what is indexed without waiting for large ingest runs. |

## Memory Quality Backlog (M-series)

Cross-reference with active roadmap above. Pull into active roadmap as core loop is validated.

| # | Feature | P-ref | Current Gap |
| --- | --- | --- | --- |
| M1 | Query-shape-aware selection | P14 (all forms reverted) | Counting queries cut atoms needed for aggregation. AGGREGATION bypass already in `select()`. Extend per-shape rules post-P25 removal. |
| M2 | Multi-session aggregation fix | — | "How many times?" misses cross-session atoms; fine filter cuts needed atoms for counting. Partially addressed by AGGREGATION bypass + M9 numeric extraction. |
| M3 | Source citations | — | ✅ shipped — numbered superscript citations, pulsing highlight linkage, collapsible sources section. |
| M4 | Memory debug mode | P18 | BM25 scores, BFS paths, fallback triggers visible in web UI. See active roadmap. |
| M5 ✅ | Dense seed augmentation | P16 | Shipped. BAAI/bge-small-en-v1.5 sidecar. `LATTICE_DENSE_SEEDS=1`. Preference +16.7pp (p34). |
| M6 | Semantic relation enrichment | P13 | `updates`, `contradicts`, `supports` edges for richer multi-hop. See active roadmap. |
| M7 | Topic hubs | P21 | Broad queries land on concept clusters before atoms. See active roadmap. |
| M8 | Ingest job status | P12 | Visibility into what's indexed, pending, failed. See active roadmap. |
| M9 ✅ | Extraction precision: numeric values + proper nouns | — | Shipped as `kind=count` atom type. +4pp overall (p27). |
| M10 | Contradiction vs supersession | — | Conflicting same-date atoms incorrectly superseded; explicit contradiction path keeps both with `contradicts` edge. Depends on M6. |
| M11 | Time decay per kind | — | Stale atoms rank identically to recent ones. See active roadmap. |
| M12 | Reinforcement counting | — | Same fact recurring across ingests lost to dedup. See active roadmap. |
| M13 | Confidence scoring at extraction | — | LLM assigns `confidence ∈ [0,1]` per atom at ingest; replaces fine filter at query time. See active roadmap. |
| M14 | Agent re-query problem | — | MCP clients re-call `lattice_select` to "verify" injected context — burns tokens, produces memory-zero behavior. Fix: explicit system prompt instruction to treat injected atoms as authoritative. Verify empirically first. |
| M15 | Session-level passive ingest | — | Inbox drop requires active habit. No ambient session extraction. Phase 2+ solution: browser extension or `lattice_capture` MCP tool at session end. |

## Removed From Active Roadmap

- **P14 query-shape selection** (all forms tried and reverted): seed reordering (p14, p16b-replay-reranked) confirmed harmful (-15pp multi-session, -23pp temporal). Token-intersection filter (p11) reverted — 67% fallback rate. Kind-proportional BFS budget (p10c) reverted. Two-stage LLM filter (p24-llmfilter) is current impl; being replaced by P25.
- Date injection into atom content: polluted content, hurt temporal/multi-session reasoning.
- Question-type prompt patches: benchmark-shaped and brittle.
- HyDE over BM25: hallucinated vocabulary hurt sparse retrieval.
- Generated questions per atom: polluted BM25 with false positives.
- Session summary atoms: LongMemEval-shaped; topic hubs are the product-native version.
- Multi-pass retrieval and uncertainty-triggered re-retrieval: brittle; pack retrieval and graph selection solve the product problem first.
- **P15 ingest tool calling** (reverted): 3x latency (~60s/q vs ~19s/q). Worth revisiting for API-only providers.
- **P2 selection tool calling**: skipped — superseded by graph-seeded selection.

## LongMemEval Yardstick

LongMemEval is used to measure whether product changes improve retrieval and answer quality under long-memory pressure. It should not dictate architecture.

**Current baseline: p27 — 76%**
- ingest: `gpt-4o-mini` via OpenRouter, 3192 atoms (~31.9/session), 100 sessions — with `kind=count` numeric extraction
- selection: `_retrieve()` + score>0 seed filter + BFS rescore — 0 LLM calls/query (P25 ablation C winner)
- synthesis: `gpt-4o-mini` via OpenRouter — prefers `kind=count` atoms for counting queries
- judge: `phi4-mini-judge`
- lattice dirs: `results/p27/openaigpt4omini_longmemeval_oracle_inference.lattices`
- code: `sandbox` branch (`LATTICE_SEED_MIN_SCORE=0.001`, `LATTICE_BFS_RESCORE=1`)

**Previous baseline: 76% / 79.9% task-avg** (p24-llmfilter)
- ingest: `qwen3-8b-ingest` (qwen atoms, ~33/session)
- selection: `qwen3.5:4b` two-stage LLM filter
- synthesis: `qwen3.5:4b`
- judge: `phi4-mini-judge`
- lattice dirs: `results/p21-broad-subjects/` (reused)

Observed failure modes (current, p26c baseline):
- **Single-session-preference (50%)**: biggest gap. Zero-score seed filter drops low-frequency preference atoms (e.g. "I prefer X") that BM25 scores weakly. Fix: M11 time decay or M13 confidence scoring to surface preference atoms without LLM overhead.
- **Temporal reasoning (65%)**: BFS rescore deprioritises temporally-relevant atoms that score lower on BM25. M11 time decay per kind would help without reranking.
- **Multi-session recovered to 67%** with BFS rescore — cross-session atoms now surface via higher BM25 score post-expansion.
- **Ingest recall**: gpt-4o-mini extracts ~31.3 atoms/session vs qwen 33/session. Numeric facts still missed (M9).

Evaluation method:
- Implement one product priority at a time.
- Run full 100-question LongMemEval.
- Compare overall score and category movement.
- Keep product-fit changes even if benchmark movement is mixed; do not optimize architecture solely for LongMemEval.

## Experiment History (last 10 runs)

| Run | Change | Accuracy | Notes |
| --- | --- | --- | --- |
| p12-5b | Source-aware parsing layer (parsers/) + P10 proper-noun recommendation rule + qwen3.5:4b synthesis, fresh ingest | **78.0%** | +2pp vs 76% replay baseline. temporal +11.5pp (73.1%→84.6%), single-session-user +7pp. knowledge-update -12.5pp and single-session-assistant -9pp — ingest noise + supersession fragility, not parsers. |
| p17 | sum_numbers tool + counting/rounding guidance in synthesis (replay p12-5b atoms) | **79.0%** | +1pp. single-session-assistant +18pp (54.5%→72.7%), knowledge-update +6pp. temporal -7.7pp — synthesis using observed_at instead of event dates in date_diff (pre-existing fragility). |
| p18 | Written-number date resolution + synthesis empty-response fix, fresh ingest | **73.0%** | -6pp vs p17. 4 temporal recoveries from _resolve_dates fix. Regressions are ingest variance (multi-session -14.8pp, single-session-user -14.3pp), not from the fix. |
| p19 | Switch ingest to `qwen3-8b-ingest`, fresh ingest | **73.0%** | 3329 atoms (33.3/session) vs 1837 (18.4/session). BM25 recall 1.000→0.976. multi-session +7pp, single-session-user +14pp. single-session-preference -33pp, temporal -12pp — synthesis variance on fresh ingest. |
| p19-replay | Replay synthesis over fixed p19 qwen atoms | **72.0%** | Isolates synthesis variance. single-session-assistant +27pp (63.6→90.9%). multi-session -11pp, knowledge-update -19pp. qwen atom set stable; selection bottleneck at 29 avg atoms to synthesis. |
| p21-broad-subjects | Broad topic hubs: general subject labels → `same_subject_as` edges across sessions | **67.0%** | -6pp. multi-session -15pp — broad edges over-connect unrelated sessions, flooding synthesis. Confirmed: broad `same_subject_as` hurts precision more than recall. |
| p22-agent | LLM selection agent: search/expand/finish tools with query-type hints | **73.0%** | task-avg 75.1% (best then). single-session-assistant 100%, temporal 84.6%. multi-session 51.9% — agent skips expand (74% queries: search→finish). `SELECTION_MODEL=qwen3.5:4b`. |
| p23-autoexpand | Intent-gated auto-expand in agent: force `expand` for knowledge-update + preference queries | **69.0%** | -4pp. Keyword triggers fired for ALL preference queries including single-session → flooded synthesis. Agent formulation abandoned. |
| p24-llmfilter | Two-stage LLM filter: BM25+BFS → coarse (subject+kind, 8–25) → fine (full content, 5–15). Pydantic grammar constraints. `SELECTION_NUM_CTX=8192`. | **76.0%** | task-avg **79.9% (best)**. knowledge-update +12.5pp, preference +16.7pp, temporal +7.7pp. multi-session flat (51.9%). 0/100 fallbacks; fine avg 8.6 atoms. |
| sandbox-replay | Verify sandbox refactors: JSON mode prompt fix, `atom_id` citation key. Replay p21 atoms. `gpt-4o-mini` selection + synthesis via OpenRouter. | **70.0%** | task-avg 72.2%. Lower than p24 — gpt-4o-mini synthesis vs qwen3.5:4b; p21 atom set. JSON mode fix + citation key confirmed working. |
| p25 | Fresh ingest with `gpt-4o-mini` via OpenRouter. p25 atoms (~31.3/session). AGGREGATION query-shape bypass (skip fine filter for counting queries). | **71%** | task-avg TBD. **New baseline** — gpt-4o-mini ingest + inference via OpenRouter. single-session-user 100%, single-session-assistant 100%, single-session-preference 83%. multi-session 59%, temporal 58%, knowledge-update 63%. -5pp vs p24 on different atom set. |
| p26a | P25 ablation A: LLM filter removed, `select()` = `_retrieve()`. 0 LLM calls/query. Reused p25 lattice dirs. | **71%** | Flat overall vs p25. temporal +11pp (69%), knowledge-update +6pp (69%), single-session-assistant 100%. single-session-user -14pp (86%), single-session-preference -16pp (67%), multi-session -3pp (56%). |
| p26b | P25 ablation B: score>0 seed filter (`LATTICE_SEED_MIN_SCORE=0.001`). Reused p25 lattice dirs. | **70%** | -1pp vs A. temporal +4pp (73%), multi-session +3pp (59%). knowledge-update -13pp (56%), single-session-preference -17pp (50%). Zero-score seed filtering hurts sparse/preference queries. |
| p26c | P25 ablation C: score>0 seeds + BFS rescore (`LATTICE_BFS_RESCORE=1`). Reused p25 lattice dirs. **Winner.** | **72%** | +1pp vs A. multi-session +11pp (67%), knowledge-update 69%. temporal -4pp (65%) vs B. single-session-preference still 50%. Production defaults: `LATTICE_SEED_MIN_SCORE=0.001` + `LATTICE_BFS_RESCORE=1`. |
| p26d | P26d: mode-conditional filter — score>0 only in EXPANSION, POINTED keeps all seeds. Reused p25 lattice dirs. **Reverted.** | **71%** | -1pp vs p26c. preference +17pp (67%), temporal +8pp (73%). multi-session -15pp (52%) — pointed mode passing noisy seeds floods BFS. p26c config restored. |
| p27 | M9: `kind=count` atom type for aggregate numeric facts at ingest. Synthesis prefers `kind=count` over re-enumeration. Fresh ingest (3192 atoms, ~31.9/session). | **76%** | +4pp vs p26c. preference +33pp (83%), knowledge-update +13pp (81%), temporal +4pp (69%), single-session-user +7pp (93%). multi-session -4pp (63%), single-session-assistant -9pp (91%). Counting no longer the bottleneck. |
| p28 | P26e: synthesis prompt — force event-date endpoints for durations + week/month unit conversion. Replay p27 atoms. **Reverted.** | **70%** | -6pp vs p27. temporal -12pp (58%), knowledge-update -13pp (69%). Overcorrected: event-date forcing breaks today-relative queries. p27 config restored. |
| p27b | **Clean baseline**: p27 atoms + current code (with `_is_no_answer()`). `LATTICE_TIME_DECAY=0`. Reused p27 lattice dirs. | **68%** | p27 (76%) was stale — run before `_is_no_answer()` added. Code drift caused 8pp gap. p27b is now the canonical oracle baseline. knowledge-update 75%, temporal 69.2%, multi-session 51.9%, preference 50%. |
| p29 | M11: time decay per kind (`LATTICE_TIME_DECAY=1`). Reused p27 lattice dirs. | **68%** | Identical to p27b on oracle subset — `as_of` anchor collapses decay to ≈1.0 for all atoms. 11/12 score changes due to synthesis stochasticity, not selection. Oracle cannot measure M11. |
| p30-baseline | **LongMemEval-S KU-wide** (34 KU questions, 90-304d spread, 550-640 atoms each). `LATTICE_TIME_DECAY=0`. Fresh ingest from longmemeval_s_cleaned.json. | **61.8% (KU only)** | Proper M11 testbed: cap-binding atom counts (>60), multi-session with wide date spreads, meaningful decay ratios (0.75-0.90 old vs 0.99 new). |
| p30-m11 | Same as p30-baseline with `LATTICE_TIME_DECAY=1`. | **73.5% (KU only)** | **+11.8pp vs baseline**. M11 confirmed: time decay reorders seeds → fresh atoms fill 60-atom BFS cap first → stale old-version facts pushed out. Validated and shipped. |
| p32 | **LongMemEval-S stratified baseline** (30/category, n=176 after 4 ingest errors). Fresh S-version ingest. `LATTICE_TIME_DECAY=1`. | **63.1%** | First cross-category S-version measurement. Preference 33.3%, temporal 51.7% — dominant failure mass. Retrieval: BM25 hit=94.4%, selected barely changes BFS. 4 large-haystack questions (44–53 sessions) hit LLM output limits, removed. |
| p33 | Synthesis prompt: clarified `valid_from`/`observed_at`, added ordering + preference grounding. Reused p32 lattice dirs. **Reverted.** | **63.6%** | +0.5pp overall, all deltas within SE (±3.8%). No statistically significant change. Reverted to p32 prompt. |
| p34 | **M5 dense seed augmentation** (`LATTICE_DENSE_SEEDS=1`, BAAI/bge-small-en-v1.5). Reused p32 lattice dirs. | **67.8%** | **+4.7pp overall**. Preference +16.7pp (33.3%→50.0%), single-session-user +6.6pp, single-session-assistant +6.7pp. Preference Hit 76.7%→93.3% — vocab-mismatch atoms now retrieved. Temporal −5.0pp is noise (n=30 vs 29 + 4 extra zero-scored questions). Shipped. |

## Category Tracker (last 10 runs)

Note: phi4-mini-judge throughout. p19+ use qwen3-8b-ingest. p25 uses gpt-4o-mini ingest.

| Category | p27b (oracle) | p30-m11 (S-KU) | p32 (S-baseline) | p33 (S-prompt) | **p34 (S-dense)** |
| --- | --- | --- | --- | --- | --- |
| overall | 68.0% | 73.5%† | 63.1% | 63.6% | **67.8%** |
| single-session-preference | 50.0% | — | 33.3% | 33.3% | **50.0%** |
| temporal-reasoning | 69.2% | — | 51.7% | 48.3% | 46.7% |
| multi-session | 51.9% | — | 63.0% | 70.4% | 66.7% |
| knowledge-update | 75.0% | **73.5%** | 70.0% | 66.7% | 70.0% |
| single-session-user | 78.6% | — | 76.7% | 80.0% | **83.3%** |
| single-session-assistant | 90.9% | — | 83.3% | 83.3% | **90.0%** |

†p30-m11 is knowledge-update only (34-question LongMemEval-S subset). S-version runs use stratified 30/category.

## Archived: Completed P1–P17

| Priority | Change | Outcome |
| --- | --- | --- |
| P1 ✅ | Product documentation cleanup | Docs reflect local-first architecture. |
| P2 ⏭️ | Selection tool calling | Skipped — superseded by graph-seeded selection. |
| P3 ✅ | Source-aware ingest + provenance + exact dedup | Atoms carry full provenance; duplicates skipped at ingest. |
| P3.5 ✅ | Retrieval oracle diagnostics + payload normalization | select/BM25 payload-shape confound cleared; session-level retrieval metrics added. |
| P4 ✅ | Pack retrieval over BM25 seeds | 13%→18%. Avg selected atoms 17→31. |
| P5 ✅ | Incremental heterogeneous graph index | NetworkX MultiDiGraph with portable sidecars; deterministic nodes/edges. |
| P6 ✅ | Graph-seeded BFS selection | 18%→19%. BFS expands evidence packs through graph edges. |
| P7 ✅ | Role-aware ingest + synthesis agent + date_diff tool | 19%→49% (phi4). Temporal 0%→38.5%. Avg atoms/session 4→14. |
| P8 ✅ | Ingest date resolution fixes | 49%→62%. Temporal 38.5%→65.4% (+27pp). |
| P9 ✅ | Fuzzy supersession via rapidfuzz token_sort_ratio | 62%→69%. knowledge-update +37pp. |
| P10.5 ✅ | Synthesis model: qwen3.5:4b via SYNTHESIS_MODEL | 69%→76% (+7pp). Stable ≤1pp variance across 3 runs. |
| P10 ✅ | Named-item recommendation extraction + unconditional cap (max 5) | Kept as product improvement; eval inconclusive (p9-base has 1 recommendation atom). |
| P12.5 ✅ | Source-aware parsing layer (parsers/) | chat/markdown/code parsers. Role+turn preserved. Normalized segment interface. |
| P15 ⏭️ | Ingest tool calling | Reverted: 3x latency. Worth revisiting for API-only providers. |
| P17 ✅ | sum_numbers tool + counting/rounding guidance | single-session-assistant +18pp. Numeric aggregation questions answered correctly. |
