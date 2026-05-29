# lattice Product Priorities

Goal: build a local-first MCP server for persistent, inspectable knowledge that works well with coding assistants and local models. LongMemEval is an evaluation yardstick, not the product target.

Product constraints:

- Local-only: no hosted service, no required daemon, no external database.
- Works with API models and Ollama; expensive enrichment must be optional.
- Atom files remain human-readable and git-trackable.
- Ingest can handle many local sources, but useful partial memory should commit quickly.
- Selection should be fast, graph-aware, and should not wait for active ingest or background enrichment.

## Completed (P1–P9, P10.5)

| Priority | Change | Outcome |
| --- | --- | --- |
| P1 ✅ | Product documentation cleanup | Docs reflect local-first architecture, not benchmark-preservation. |
| P2 ⏭️ | Selection tool calling | Skipped — useful before graph-seeded selection but deprioritized. |
| P3 ✅ | Source-aware ingest + provenance + exact dedup | Atoms carry full provenance; duplicates skipped at ingest. |
| P3.5 ✅ | Retrieval oracle diagnostics + payload normalization | select/BM25 payload-shape confound cleared; session-level retrieval metrics added. |
| P4 ✅ | Pack retrieval over BM25 seeds | 13%→18% overall. Avg selected atoms 17→31. |
| P5 ✅ | Incremental heterogeneous graph index | NetworkX MultiDiGraph with portable sidecars; deterministic nodes/edges. |
| P6 ✅ | Graph-seeded BFS selection | 18%→19%. BFS expands evidence packs through graph edges. |
| P7 ✅ | Role-aware ingest + synthesis agent + date_diff tool | 19%→49% (phi4 judge). Temporal 0%→38.5%. Avg atoms/session 4→14. |
| P8 ✅ | Ingest date resolution fixes | 49%→62%. Temporal 38.5%→65.4% (+27pp). observed_at as date ref. |
| P9 ✅ | Fuzzy supersession via rapidfuzz token_sort_ratio | 62%→69%. knowledge-update +37pp. Fuzzy subject matching catches phrasing drift. |
| P10.5 ✅ | Synthesis model upgrade: qwen3.5:4b replaces gemma4:e4b for synthesis | 69%→76% (+7pp). Stable across 3 runs (variance ≤1pp). knowledge-update 100%, single-session-user 85.7%, temporal 73.1%. `SYNTHESIS_MODEL=qwen3.5:4b` env var; gemma4:e4b retained for ingest/select. |

## Active Roadmap

Reordered after p19/p19-replay experiments. **Ingest model switched to `qwen3-8b-ingest`** (INGEST_MODEL env var): extracts ~33 atoms/session vs gemma's ~18, better coverage for multi-session/assistant categories. Tradeoff: more atoms → selection must filter harder or synthesis gets noisy context. P14 (query-shape-aware selection) is now the top priority — it was low-impact with 18 atoms/session but becomes critical at 33. Remaining gaps: multi-session 59.3%, single-session-assistant 63.6%, temporal 73.1%.

| Priority | File(s) | Product Change | Why It Matters |
| --- | --- | --- | --- |
| P10 ✅ | `ingest.py`, `selection.py` | **Assistant-turn extraction + recommendation cap**: (1) Extract user-specific assistant outputs (named products, places, techniques recommended to this user) as `kind=recommendation` atoms — distinct from generic advice that applies to anyone. (2) Unconditional post-BFS cap: max 5 `kind=recommendation` slots (tunable via `LATTICE_RECOMMENDATION_CAP`). | single-session-assistant is 63.6% — weakest non-abstention category. Two prior attempts reverted: atom explosion (p10), then correct extractions but no cap crowded selection (p10b). Both sub-tasks land together. Eval inconclusive via replay (p9-base has no recommendation atoms to cap); real effect visible on fresh ingest. |
| P12.5 ✅ | `lattice/parsers/`, `ingest.py` | **Source-aware parsing layer**: structured pre-ingest stage — chat parser (role+turn), markdown parser (section boundaries), code parser (symbol boundaries). Normalized segment interface: `{text, role, source_type, metadata}`. New source types added as parsers, not prompt changes. | Makes P10 user-vs-assistant distinction structural, not heuristic. Prerequisite for reliable multi-source ingest and multi-session coverage. |
| P14 | `selection.py`, `lattice/query.py` | **Query-shape-aware retrieval**: detect query shape (temporal / preference / recommendation / factual). Post-BFS: (1) recommendation cap (5 slots) for non-recommendation queries; (2) kind-fallback graph scan via `db.list_by_kind()` when primary-kind count == 0. Pre-BFS seed reordering confirmed harmful — post-BFS contract only. | With qwen ingest at 33 atoms/session (vs 18 with gemma), selection passes ~29 atoms to synthesis — too noisy. Query-shape cap filters this down to relevant atoms per query type. Was low-impact at 18 atoms; now critical. |
| P16 ⏭️ | `llm.py`, `db.py`, `selection.py` | **Hybrid BM25+dense seed retrieval** (seed stage only): augment BM25 seeds with dense nearest-neighbour hits before BFS. Portable embedding sidecars via `embed.py`. | qwen ingest recall is 0.976 (misses 2-3 answer atoms per 100q) vs gemma's 1.000. BM25 vocabulary mismatch still root cause. Output reranking and pre-BFS seed reordering both confirmed harmful; only seed *augmentation* is safe. `embed.py` kept. |
| P11 ⏭️ | `selection.py`, `lattice/query.py` | **Retrieval topic drift fix**: subject-match filter or query-subject overlap scoring after BFS, informed by embeddings from P16. | Token-intersection filter reverted (67% fallback rate, BFS reorder broke multi-session -22pp). Embeddings make subject matching robust. `query.py` scaffolded with `QueryIntent`/`parse_query`. |
| P13 | `graph.py`, `db.py`, `ingest.py`, `selection.py` | **Optional semantic relation enrichment**: high-confidence edges after graph indexing: `updates`, `contradicts`, `supports`, `elaborates`, `temporally_before`. Off by default for Ollama. | Deeper graph paths for multi-session aggregation without blocking local ingest/query. |
| P12 | `ingest.py`, `server.py`, `db.py` | **Local ingest jobs + status UX**: persistent status: `job_id`, indexed/active/failed source counts, `graph_version`, `last_commit_at`. | Product UX — local users need visibility into what is indexed without waiting for large ingest runs. |
| P17 ✅ | `synthesis.py` | **sum_numbers tool + counting/rounding guidance**: `sum_numbers(numbers[])` tool for exact numeric aggregation; enumerate-then-count prompt for counting questions; round week/month durations to nearest integer. | single-session-assistant +18pp (54.5%→72.7%). Full product answer contract (citations, uncertainty) deferred. |
| P21 | `graph.py`, `selection.py` | **Topic hubs / community index**: hub nodes from connected components; store aliases, member atoms, latest `observed_at`, centroid text. Depends on P13. | Broad queries land on coarse concepts before drilling into atoms. |
| P18 | `selection.py`, `server.py` | **Selection debug/status mode**: graph version, BM25 ranks/scores, BFS expansion paths, fallback trigger, include reasons. | Makes memory behavior explainable during debugging. |
| P19 | `selection.py`, `synthesis.py`, `server.py` | **Source-grounded answer mode**: citations/snippets via `source_title`, `source_id`, `source_span`. | Builds user trust. |
| P20 | `db.py`, `server.py` | **Memory namespaces**: project/workspace isolation via `LATTICE_NAMESPACE`. | Prevents cross-project contamination. |
| P15 ⏭️ | `ingest.py` | **Ingest tool calling**: `record_atom(...)` tool calls per atom; JSON fallback for local models. | Confirmed working but reverted: 3x latency (~60s/q vs ~19s/q). Worth revisiting for API providers (Anthropic/OpenAI) only. |

## Removed From Active Roadmap

- Date injection into atom content: polluted content, hurt temporal/multi-session reasoning.
- Question-type prompt patches: benchmark-shaped and brittle.
- HyDE over BM25: hallucinated vocabulary hurt sparse retrieval.
- Generated questions per atom: polluted BM25 with false positives.
- Session summary atoms: LongMemEval-shaped; topic hubs are the product-native version.
- Multi-pass retrieval and uncertainty-triggered re-retrieval: brittle; pack retrieval and graph selection solve the product problem first.

## LongMemEval Yardstick

LongMemEval is used to measure whether product changes improve retrieval and answer quality under long-memory pressure. It should not dictate architecture.

Current baseline:

- **76% accuracy / 79.9% task-avg** (p24-llmfilter, reused p21 lattice dirs, qwen3.5:4b two-stage LLM filter + synthesis), 100 questions
- inference: `qwen3-8b-ingest` (ingest) + `qwen3.5:4b` (selection filter + synthesis)
- judge: `phi4-mini-judge` (phi4-mini with num_ctx=4096 Modelfile)
- harness: `longmemeval_oracle`
- lattice dirs: `results/p21-broad-subjects/` (reused — qwen-ingested, 33 atoms/session)
- previous baseline: p22-agent, 73% overall / 75.1% task-avg

Note: switched ingest model to `qwen3-8b-ingest` after p19/p19-replay experiments. qwen extracts ~33 atoms/session vs gemma's ~18, improving coverage but requiring stronger selection filtering. p19-replay (same atoms, fresh synthesis) scored 72% — confirms atom set is stable, category swings in p19 vs p18 were synthesis variance. Selection is the next bottleneck.

Note: p24-llmfilter 100% single-session-assistant matches p22-agent. Two-stage LLM filter with Pydantic grammar constraints achieves 0/100 fallbacks and avg 8.6 fine atoms. Multi-session aggregation is the remaining ceiling: 13/27 failures are counting/total questions where fine filter cuts atoms needed for full enumeration (e.g. 92 total_selected → fine=7). Fix candidate: skip fine filter for detected aggregation queries, or raise fine min to all coarse atoms for "how many / total" query shapes.

Note: the original P9 run scored 69% — a lucky ingest run. A fresh ingest with identical code gives 62%. Ingest non-determinism produces ~7pp overall variance and up to 19pp on individual categories.

Note: earlier runs used `qwen3.5:4b` as judge, which severely underscored correct answers (especially temporal and abstention). phi4-mini-judge is the canonical judge going forward. P7 and P8 have been re-judged with phi4-mini.

Observed failure modes:

- **Synthesis variance resolved (P10.5)**: qwen3.5:4b stable at 76% ±1pp across 3 runs. gemma4:e4b variance (7pp overall, 19pp per category) is no longer the bottleneck.
- **Selection now the bottleneck**: qwen ingest produces ~33 atoms/session; selection passes avg 29 to synthesis. Too many atoms → noisy synthesis context. P14 filtering now critical.
- **qwen ingest recall 0.976**: misses 2-3 answer atoms per 100q (vs gemma 1.000). BM25 vocabulary mismatch still present; P16 dense seed augmentation addresses this.
- 20% of questions: selection returns 0 atoms despite 26+ atoms created.
- 24% of questions: atoms selected but synthesis still wrong (down from 56% at gemma baseline).
- Multi-session and single-session-assistant remain the weakest categories — aggregation and assistant-turn extraction are the remaining bottlenecks.
- `answer_session_ids` are available across local oracle/S/M datasets and now provide session-level retrieval diagnostics; `has_answer` is available on gold sessions and is exposed for debugging, but exact turn-level metrics still require turn-span provenance.

Evaluation method:

- Implement one product priority at a time.
- Run full 100-question LongMemEval.
- Compare overall score and category movement.
- Keep product-fit changes even if benchmark movement is mixed, but do not optimize architecture solely for LongMemEval.

## Experiment History

| Run | Change | Accuracy | Notes |
| --- | --- | --- | --- |
| baseline | none | 15.0% | `gemma4:e4b` inference, `qwen3.5:4b` judge, 100q oracle |
| p1 | Synthesis CoT | 23.8% | Best measured gain so far; task-avg 25.2%, multi-session 22.2%, temporal 7.4%. |
| p2 | Date injection into atom content | 19.0% | Helped some direct categories but regressed overall; content pollution. Reverted. |
| p3 | Question-type-aware selection prompt | 18.0% | Prompt-only benchmark patch regressed overall. Reverted. |
| p4 | HyDE expansion | skipped | BM25 + hallucinated vocabulary produced wrong retrieval; better suited for dense retrieval. |
| p5 | Generated questions per atom | 16.0% | Generated questions polluted BM25 with false-positive matches. Reverted. |
| p6 | Adaptive paragraph chunking | 22.0% | Helped some user-fact extraction but hurt cross-paragraph/coreference cases. Keep only as motivation for source-aware segmentation. |
| p3.5-select | Retrieval oracle + selected payload normalization | 13.0% | Verified select/BM25 payload-shape confound cleared on reused P3 lattices. Retrieval metrics matched BM25 exactly: selected hit 100%, recall 1.000, precision 1.000, MRR 1.000. Task-avg 15.03%. |
| p3.5-bm25 | BM25 ablation on normalized payload | 15.0% | Same reused P3 lattices and current diagnostics. BM25 hit 100%, recall 1.000, precision 1.000, MRR 1.000. Task-avg 17.51%. |
| p4-pack | Pack retrieval over BM25 seeds | 18.0% | Product-fit keeper. Avg selected atoms rose from 17.1 to 31.1. Selected hit 100%, recall 0.986, precision 1.000, MRR 1.000. Task-avg 20.19%. |
| p6-graph | Graph BFS selection (P5+P6) | 19.0% | Overall +1pp, task-avg 21.81%. knowledge-update 43.75% (↑↑ from 25%). multi-session dropped to 11.1%. temporal-reasoning still 0% — null valid_from is root cause. |
| p7 | Role-aware ingest + synthesis agent + query_date fix | 30.0% (qwen) / **49.0% (phi4)** | qwen judge: overall +11pp, task-avg 30.4%. phi4 judge: 49.0%, task-avg 49.8%. temporal 38.5%, knowledge-update 68.75%, multi-session 48.1%. Avg atoms/session 4→14. |
| p8 | Ingest date resolution fixes (observed_at as ref, today pattern, preserve explicit dates) | **62.0% (phi4)** | Overall +13pp over p7 (phi4 judge). task-avg 60.1%. temporal 38.5%→65.4% (+27pp). knowledge-update 68.75%→56.25% (-12pp, supersession chain disruption). multi-session 62.9%. abstention 100%. |
| p9 | Fuzzy supersession via rapidfuzz token_sort_ratio (threshold=80, env-tunable) | **69.0% (phi4)** | Overall +7pp. task-avg 66.75%. knowledge-update 56.25%→93.75% (+37pp — fuzzy matching correctly catches subject-phrasing drift). multi-session 74.1% (+11pp). 4 true regressions vs P8, none caused by fuzzy matching: 2 assistant-turn extraction failures (P10 fix) and 2 fragile synthesis cases. |
| p10 | Assistant-turn extraction (reverted) + synthesis preference/recommendation guidance | **62.0% (phi4)** | Reverted to P9 baseline. Ingest loosening caused recommendation atom explosion (up to 59/109 atoms from assistant turns); LLM couldn't distinguish generic advice from user-specific output. single-session-assistant +54pp but multi-session -19pp, knowledge-update -25pp, single-session-user -21pp. Synthesis kind=preference/recommendation guidance kept — low-risk, no measurable harm. |
| p11 | Token-intersection seed filter via `lattice/query.py` (reverted) | **61.0% (phi4)** | -8pp overall. 21 regressions, 13 recoveries. Two failure modes: (1) filter dropped valid on-topic seeds due to subject vocab mismatch → lost BFS context (7 cases); (2) changed BFS entry points reshuffle multi-session evidence packs (11 cases). Token intersection fires reliably only for named-entity queries; too blunt for general subjects. `query.py` module kept for P14/P18. |
| p16b | Post-BFS embedding rerank via fastembed BAAI/bge-small-en-v1.5 (reverted) | **67.0% (phi4)** | -2pp vs P9 baseline but 98% of atom sets differed due to ingest non-determinism — result within noise. |
| p16b-replay (control) | Replay synthesis over identical p9 atoms, original BFS order | **68.0% (phi4)** | Isolated synthesis variance from ingest noise. task-avg 68.49%. single-session-preference +17pp, temporal +8pp vs P9. multi-session -15pp (synthesis variance). |
| p16b-replay-reranked | Replay synthesis over identical p9 atoms, embedding-reranked order | **62.0% (phi4)** | -6pp vs control. temporal-reasoning 73%→50% (-23pp). Confirms output reranking breaks date-chain atoms that need graph/chronological order. knowledge-update 87.5%→93.75% (+6pp — most-recent atom first helps). Embedding rerank definitively harmful for synthesis order. |
| p10b | Few-shot examples + named-item rule for assistant extraction (reverted) | **62.0% (phi4)** | single-session-assistant +45pp (36%→82%) but multi-session -22pp, knowledge-update -18pp, single-session-user -14pp. Recommendation atoms flood selection budget → crowd out event/fact atoms. Fix requires query-intent-aware selection (P14). |
| p10c | Kind-proportional BFS budget (reverted) | **65.0% (phi4)** | Tried to fix P10b crowding via seed kind distribution → budget. Preference -17pp, knowledge-update -6pp. BM25 seeds are noisy intent signal — preference queries surface fact/event seeds. Reverted both P10b ingest and P10c selection. |
| p14 | Query-shape seed reordering + recommendation cap (both reverted) | **62.0% (phi4)** | Seed reordering: put primary-kind seeds first in BFS → multi-session -15pp. Same fragility as P16b reranking. Recommendation cap also reverted — zero-cost with P9 atoms but will be re-implemented with P10 ingest. |
| p9-base | Clean P9 re-run with --keep-lattice-dirs (canonical baseline) | **62.0% (phi4)** | Fresh ingest, same P9 code. Atom distributions nearly identical to original p9 (69%) run — avg 14.8 atoms/q, same kind ratios. 7pp gap vs original p9 is pure synthesis variance. Lattice dirs kept at results/p9-base/...lattices/ for controlled selection/synthesis experiments. |
| p9-base-t0 | Replay over p9-base atoms, synthesis temperature=0 | **63.0% (phi4)** | Ollama ignores temperature=0 — gemma4:e4b still produces different outputs. Multi-session +7pp, knowledge-update +6pp vs p9-base but single-session-user -7pp. Category swings up to 7pp from synthesis variance alone. |
| p9-base-mv | Replay over p9-base atoms, 3-vote majority vote (fuzzy via rapidfuzz) | **63.0% (phi4)** | Majority vote picks most "central" answer across 3 parallel synthesis calls. Multi-session +15pp vs p9-base run1 but knowledge-update -6pp. Overall still 63% — synthesis variance irreducible at this model scale. gemma4:e4b produces genuinely different interpretations, not just rephrasing. |
| p10-5 | Synthesis model upgrade: qwen3.5:4b via `SYNTHESIS_MODEL` env var, p9-base atoms | **76.0% (phi4)** | +7pp vs p9-base gemma. knowledge-update 100%, single-session-user 85.7%, temporal 73.1%, multi-session 66.7%. 100/100 completed, no hangs. |
| p10-5b | Replication: same config, fresh run | **76.0% (phi4)** | Confirms p10-5 not a lucky run. Variance ≤1pp. |
| p10-5c | Replication: replay over p9-base atoms | **76.0% (phi4)** | Confirms stability independent of ingest path. 3 consecutive runs at 76% — synthesis variance resolved. |
| p10 | Named-item recommendation extraction rule + unconditional cap (max 5 recommendation atoms) | **74.0% (phi4)** | -2pp vs p10-5c baseline, within synthesis variance (6 regressions, 4 recoveries, none caused by cap). p9-base has 1 question with recommendation atoms; cap was a no-op. Ingest rule untestable via replay — effect will show on fresh ingest. Changes kept as product improvements. |
| p12-5b | Source-aware parsing layer (parsers/) + P10 proper-noun recommendation rule + qwen3.5:4b synthesis, fresh ingest | **78.0% (phi4)** | +2pp vs 76% replay baseline, +9pp vs P9 (69%). temporal-reasoning +11.5pp (73.1%→84.6%), single-session-user +7pp (85.7%→92.9%), multi-session +3.7pp. knowledge-update -12.5pp (100%→87.5%) and single-session-assistant -9pp (63.6%→54.5%) — both from fresh ingest noise + supersession fragility, not from the new parsers. |
| p17 | sum_numbers tool + counting/rounding guidance in synthesis (replay over p12-5b atoms) | **79.0% (phi4)** | +1pp overall vs p12-5b. single-session-assistant +18pp (54.5%→72.7%), knowledge-update +6pp (87.5%→93.75%). temporal-reasoning -7.7pp (84.6%→76.9%) — caused by synthesis using observed_at instead of event dates in date_diff calls (pre-existing fragility, not regression from this change). sum_numbers tool firing correctly on numeric aggregation questions. |
| p18 | Written-number date resolution ("a week ago", "two months ago") + synthesis empty-response fix (re-prompt after tool calls return empty), fresh ingest | **73.0% (phi4)** | -6pp vs p17b. Temporal unchanged at 76.9% — target category. 4 temporal recoveries from _resolve_dates fix (incl. "two weeks ago" pattern). Regressions are ingest variance: multi-session -14.8pp, single-session-user -14.3pp. synthesis empty-response fix recovered `a08a253f` (fitness classes). Code changes correct; -6pp is non-deterministic gemma4:e4b ingest, not regression from the fix. |
| p19 | Switch ingest model to `qwen3-8b-ingest` (INGEST_MODEL=qwen3-8b-ingest), fresh ingest | **73.0% (phi4)** | Same overall as p18. qwen extracts 3329 atoms (33.3/session) vs gemma's 1837 (18.4/session) — 1.8x more. BM25 recall drops 1.000→0.976 (2-3 missed answer atoms). multi-session +7pp (55.6→63%), single-session-user +14pp (78.6→92.9%). single-session-preference -33pp (83.3→50%), temporal -12pp (76.9→65.4%) — both synthesis variance on fresh ingest, not structural. |
| p19-replay | Replay synthesis over fixed p19 qwen atoms (reuse-lattice-root) | **72.0% (phi4)** | Isolates synthesis variance from ingest. single-session-assistant +27pp (63.6→90.9%), temporal same (76.9%). multi-session -11pp (63→51.9%), knowledge-update -19pp (100→81.25%). Category swings across p19 fresh vs p19-replay as large as p18 vs p19 — confirms p19 category shifts were synthesis variance. qwen atom set stable; selection is the bottleneck at 29 avg atoms passed to synthesis. Lattice dirs kept at results/p19/...lattices/ as new canonical baseline for selection/synthesis experiments. |
| p21-broad-subjects | Broad topic hubs: inject general subject labels ("hiking", "cooking") alongside specific subjects to create `same_subject_as` edges across sessions | **67.0% (phi4)** | -6pp regression. task-avg 69.4%. multi-session -15pp (63→48.2%) — broad subjects over-connect atoms from unrelated queries, flooding synthesis with cross-session noise. single-session-assistant +18pp (63.6→81.8%) — accidentally helps by adding subject edges within a session. Confirmed: broad same_subject_as edges hurt precision more than they help recall. |
| p22-agent | LLM-driven selection agent: search/expand/finish tools with query-type hints; safety net fallback when agent under-retrieves | **73.0% (phi4)** | task-avg **75.1% (best)**. single-session-assistant 100% (+36pp vs p19), temporal 84.6% (+20pp). multi-session 51.9% (-11pp vs p19) — agent under-uses expand (74% of queries: search→finish without expand). knowledge-update 68.75% (-31pp vs p19) — same cause. `SELECTION_MODEL=qwen3.5:4b`. Retrieval mode `--retrieval-mode agent` in run_eval. |
| p23-autoexpand | Intent-gated auto-expand in `select_agent()`: force `expand` call in code for knowledge-update and preference queries | **69.0% (phi4)** | -4pp regression. Keyword triggers in `_needs_expand` fired for ALL preference queries including single-session → flooded synthesis with cross-session atoms. session_id diversity gate considered but rejected (LongMemEval-specific). Agent formulation abandoned. |
| p24-llmfilter | Replace `select_agent()` with two-stage LLM filter: BM25+BFS retrieval → coarse LLM filter (subject+kind, picks 8–25) → fine LLM filter (full content, picks 5–15). Pydantic structured output with Field range constraints enforced at grammar level. `SELECTION_NUM_CTX=8192`. | **76.0% (phi4)** | task-avg **79.9% (new best)**. +3pp vs p22-agent overall, +4.9pp task-avg. knowledge-update +12.5pp (68.75%→81.25%), preference +16.7pp, temporal +7.7pp. multi-session flat (51.9%). 0/100 fallbacks; fine filter avg 8.6 atoms. Remaining failures: multi-session aggregation (13 fails — fine filter cuts atoms needed for counting totals), 2–3 ingest misses (TV size/bike count not extracted), 3 knowledge-update (conflicting same-date atoms), 4 temporal (date arithmetic). |

## Category Tracker

Note: p1–p6-graph used `qwen3.5:4b` judge. p7+ use `phi4-mini-judge`. p9-base onward use fixed atoms (reused lattice dirs) — category variance reflects synthesis noise only. p10-5+ use qwen3.5:4b synthesis. p19+ use qwen3-8b-ingest.

| Category | p9-base | p10-5c (qwen synth) | p12-5b | p17 | p18 | p19 (qwen ingest) | p19-replay | p21-broad | p22-agent | p23-autoexpand | p24-llmfilter |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| overall | 62.0% | **76.0%** | 78.0% | **79.0%** | 73.0% | 73.0% | 72.0% | 67.0% | 73.0% | 69.0% | **76.0%** |
| task-avg | 60.7% | **76.0%** | 76.1% | **78.9%** | 75.3% | 72.5% | 72.8% | 69.4% | **75.1%** | — | **79.9%** |
| single-session-user | 64.3% | **85.7%** | 92.9% | 92.9% | 78.6% | **92.9%** | 85.7% | 71.4% | 78.6% | — | 78.6% |
| single-session-preference | 50.0% | **66.7%** | 66.7% | 66.7% | **83.3%** | 50.0% | 50.0% | **66.7%** | **66.7%** | — | **83.3%** |
| single-session-assistant | 45.5% | 63.6% | 54.5% | **72.7%** | 63.6% | 63.6% | **90.9%** | 81.8% | **100%** | — | **100%** |
| multi-session | 55.6% | 66.7% | 70.4% | 70.4% | 59.3% | **63.0%** | 51.9% | 48.2% | 51.9% | — | 51.9% |
| temporal-reasoning | 61.5% | 73.1% | **84.6%** | 76.9% | 73.1% | 65.4% | **76.9%** | 73.1% | **84.6%** | — | **84.6%** |
| knowledge-update | 87.5% | **100%** | 87.5% | 93.75% | 93.75% | **100%** | 81.25% | 75.0% | 68.75% | — | 81.25% |
| abstention | **100%** | **100%** | **100%** | **100%** | **100%** | **100%** | **100%** | **100%** | **100%** | — | **100%** |
