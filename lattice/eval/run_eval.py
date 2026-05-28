"""
LongMemEval evaluation harness for lattice-mcp.

Three independent phases — run them in order:

    # 1. Ingest all 100 questions, save lattice dirs
    python -m lattice.eval.run_eval --phase ingest --priority p18

    # 2. Inference: load qwen once, run select+synthesize over saved lattice dirs
    python -m lattice.eval.run_eval --phase inference --priority p18 \\
        --reuse-lattice-root results/p18/gemma4e4b_longmemeval_oracle_inference.lattices

    # 3. Judge: score hypotheses
    python -m lattice.eval.run_eval --phase judge --priority p18

Other options:
    --stratify 10               quick smoke test (10 questions)
    --retrieval-mode bm25       bypass LLM re-ranking in inference
    --retrieval-mode all        bypass retrieval; synthesize over all atoms
    --replay-debug path.jsonl   re-run synthesis over atoms from a prior debug file

Defaults (overridable via CLI flags or .env.eval):
    dataset  : lattice/eval/data/longmemeval_oracle.json
    stratify : 100 questions, stratified by question_type
    seed     : 42
    retrieval: select (BM25 + graph BFS + LLM re-rank)
    top_k    : 20
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv
from tqdm import tqdm

from lattice.db import LatticeDB
from lattice.embed import rerank_atom_dicts
from lattice.eval.session_formatter import format_session
from lattice.ingest import _parse_datetime, ingest
from lattice.selection import select, select_agent
from lattice.synthesis import synthesize

# ── config ────────────────────────────────────────────────────────────────────

_DATA_DIR = Path(__file__).parent / "data"
_DEFAULT_DATASET = str(_DATA_DIR / "longmemeval_oracle.json")


def _slug(s: str) -> str:
    for ch in (":", "/", ".", "-"):
        s = s.replace(ch, "")
    return s


def _results_dir(priority: str) -> str:
    return f"results/{priority}" if priority else "results"


def _logs_dir(priority: str) -> str:
    return f"logs/{priority}" if priority else "logs"


def _default_out(llm_model: str, dataset: str, priority: str, retrieval_mode: str = "select") -> str:
    ds = Path(dataset).stem
    suffix = "_inference" if retrieval_mode == "select" else f"_{retrieval_mode}_inference"
    return f"{_results_dir(priority)}/{_slug(llm_model)}_{ds}{suffix}.jsonl"


def _default_log(llm_model: str, judge_model: str, dataset: str, phase: str, priority: str, retrieval_mode: str = "select", ingest_model: str = "") -> str:
    ds = Path(dataset).stem
    base = _logs_dir(priority)
    mode = "" if retrieval_mode == "select" else f"_{retrieval_mode}"
    if phase == "ingest":
        ingest_slug = _slug(ingest_model) if ingest_model else _slug(llm_model)
        name = f"run_{ingest_slug}_{ds}{mode}_ingest.log"
    elif phase == "inference":
        name = f"run_{_slug(llm_model)}_{ds}{mode}_inference.log"
    elif phase == "judge":
        name = f"run_{_slug(judge_model)}_{ds}{mode}_judge.log"
    else:
        name = f"run_{_slug(llm_model)}_{_slug(judge_model)}_{ds}{mode}_all.log"
    return f"{base}/{name}"


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data: str) -> None:
        for s in self.streams:
            s.write(data)

    def flush(self) -> None:
        for s in self.streams:
            s.flush()

    def fileno(self):
        return self.streams[0].fileno()


def _load_config(args: argparse.Namespace) -> dict:
    load_dotenv(".env.eval", override=False)
    model = os.environ.get("LLM_MODEL", "qwen3.5:4b")
    ingest_model = os.environ.get("INGEST_MODEL", "")
    judge = os.environ.get("JUDGE_MODEL", "qwen3.5:4b")
    dataset = args.dataset or os.environ.get("DATASET", _DEFAULT_DATASET)
    phase = args.phase
    priority = args.priority or os.environ.get("PRIORITY", "")
    retrieval_mode = args.retrieval_mode or os.environ.get("RETRIEVAL_MODE", "select")
    if retrieval_mode not in {"select", "bm25", "all", "agent"}:
        raise ValueError("RETRIEVAL_MODE must be one of: select, bm25, all, agent")
    return {
        "dataset": dataset,
        "out": args.out or os.environ.get("OUT", _default_out(model, dataset, priority, retrieval_mode)),
        "log": args.log or os.environ.get("LOG", _default_log(model, judge, dataset, phase, priority, retrieval_mode, ingest_model)),
        "priority": priority,
        "stratify": args.stratify or int(os.environ.get("STRATIFY", "100")),
        "seed": args.seed or int(os.environ.get("SEED", "42")),
        "retrieval_mode": retrieval_mode,
        "top_k": args.top_k or int(os.environ.get("TOP_K", "20")),
        "llm_provider": os.environ.get("LLM_PROVIDER", "ollama"),
        "llm_model": model,
        "ingest_model": ingest_model,
        "judge_model": judge,
        "evaluate_script": args.evaluate_script or os.environ.get("EVALUATE_SCRIPT", ""),
        "print_qa_script": args.print_qa_script or os.environ.get("PRINT_QA_SCRIPT", ""),
        "reuse_lattice_root": args.reuse_lattice_root or os.environ.get("REUSE_LATTICE_ROOT", ""),
        "replay_debug": args.replay_debug or os.environ.get("REPLAY_DEBUG", ""),
        "replay_rerank": args.replay_rerank,
    }


# ── stratified sampling ───────────────────────────────────────────────────────


def _stratify(data: list[dict], n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    by_type: dict[str, list[dict]] = {}
    for item in data:
        by_type.setdefault(item["question_type"], []).append(item)

    total = len(data)
    sample: list[dict] = []
    remainder: list[dict] = []

    for qtype, items in by_type.items():
        quota = round(n * len(items) / total)
        shuffled = rng.sample(items, len(items))
        sample.extend(shuffled[:quota])
        remainder.extend(shuffled[quota:])

    shortfall = n - len(sample)
    if shortfall > 0:
        sample.extend(rng.sample(remainder, min(shortfall, len(remainder))))
    elif shortfall < 0:
        rng.shuffle(sample)
        sample = sample[:n]

    rng.shuffle(sample)
    return sample


# ── resume helpers ─────────────────────────────────────────────────────────────


def _load_done_ids(out_path: Path) -> set[str]:
    if not out_path.exists():
        return set()
    done = set()
    with out_path.open() as f:
        for line in f:
            try:
                entry = json.loads(line)
                if not entry.get("hypothesis", "").startswith("ERROR:"):
                    done.add(entry["question_id"])
            except Exception:
                pass
    return done


# ── debug helpers ─────────────────────────────────────────────────────────────


def _atom_debug_dict(atom, preview_chars: int | None = None) -> dict:
    content = atom.content if preview_chars is None else atom.content[:preview_chars]
    return {
        "atom_id": atom.atom_id,
        "subject": atom.subject,
        "kind": atom.kind,
        "source": atom.source,
        "content": content,
        "valid_from": atom.valid_from.isoformat() if atom.valid_from else None,
        "valid_until": atom.valid_until.isoformat() if atom.valid_until else None,
        "is_superseded": atom.is_superseded,
        "supersedes": atom.supersedes,
        "superseded_by": atom.superseded_by,
        "provenance": {
            "source_id": atom.source_id,
            "source_title": atom.source_title,
            "source_type": atom.source_type,
            "session_id": atom.session_id,
            "segment_id": atom.segment_id,
            "source_span": atom.source_span,
            "observed_at": atom.observed_at.isoformat() if atom.observed_at else None,
            "ingested_at": atom.ingested_at.isoformat() if atom.ingested_at else None,
        },
        "dedup": {
            "content_hash": atom.content_hash,
            "normalized_content_hash": atom.normalized_content_hash,
        },
    }


def _atom_session_id(atom: dict) -> str | None:
    provenance = atom.get("provenance") or {}
    return provenance.get("session_id") or atom.get("session_id")


def _session_retrieval_metrics(item: dict, atoms: list[dict]) -> dict:
    gold = set(item.get("answer_session_ids") or [])
    retrieved = [sid for atom in atoms if (sid := _atom_session_id(atom))]
    retrieved_set = set(retrieved)

    metrics = {
        "gold_answer_session_ids": sorted(gold),
        "retrieved_session_ids": retrieved,
        "retrieved_gold_session_ids": sorted(gold & retrieved_set),
        "missing_gold_session_ids": sorted(gold - retrieved_set),
        "session_hit": None,
        "session_recall": None,
        "session_precision": None,
        "session_mrr": None,
    }
    if not gold:
        return metrics

    first_rank = next(
        (i + 1 for i, sid in enumerate(retrieved) if sid in gold), None
    )
    gold_hits = [sid for sid in retrieved if sid in gold]
    metrics.update({
        "session_hit": bool(gold & retrieved_set),
        "session_recall": len(gold & retrieved_set) / len(gold),
        "session_precision": len(gold_hits) / len(retrieved) if retrieved else 0.0,
        "session_mrr": 1 / first_rank if first_rank else 0.0,
    })
    return metrics


def _answer_turn_summary(item: dict, preview_chars: int = 240) -> dict:
    sessions = item.get("haystack_sessions", [])
    session_ids = item.get("haystack_session_ids", [f"s{i}" for i in range(len(sessions))])
    answer_session_ids = set(item.get("answer_session_ids") or [])
    counts: dict[str, int] = {}
    previews: list[dict] = []

    for session, session_id in zip(sessions, session_ids):
        count = 0
        for turn_index, turn in enumerate(session):
            if turn.get("has_answer") is not True:
                continue
            count += 1
            previews.append({
                "session_id": session_id,
                "turn_index": turn_index,
                "role": turn.get("role"),
                "content": str(turn.get("content", ""))[:preview_chars],
            })
        if count:
            counts[session_id] = count

    return {
        "answer_session_ids": sorted(answer_session_ids),
        "answer_turn_counts_by_session": counts,
        "answer_turns_preview": previews,
    }


def _answer_token_recall(gold_answer: str, atoms: list[dict]) -> float:
    if not gold_answer or not atoms:
        return 0.0
    gold_tokens = set(str(gold_answer).lower().split())
    stopwords = {"i", "a", "an", "the", "is", "was", "are", "were", "of", "in",
                 "to", "and", "or", "my", "me", "you", "your", "it", "this", "that"}
    gold_tokens -= stopwords
    if not gold_tokens:
        return 0.0
    corpus_tokens: set[str] = set()
    for atom in atoms:
        corpus_tokens.update(str(atom.get("content", "")).lower().split())
    return len(gold_tokens & corpus_tokens) / len(gold_tokens)


def _new_retrieval_totals() -> dict[str, float]:
    return {"n": 0, "hit": 0, "recall": 0.0, "precision": 0.0, "mrr": 0.0}


def _add_retrieval_totals(totals: dict[str, float], metrics: dict) -> None:
    if metrics.get("session_hit") is None:
        return
    totals["n"] += 1
    totals["hit"] += 1 if metrics["session_hit"] else 0
    totals["recall"] += float(metrics.get("session_recall") or 0.0)
    totals["precision"] += float(metrics.get("session_precision") or 0.0)
    totals["mrr"] += float(metrics.get("session_mrr") or 0.0)


def _format_retrieval_totals(name: str, totals: dict[str, float]) -> str:
    n = int(totals["n"])
    if not n:
        return f"  {name:<8}: n=0"
    return (
        f"  {name:<8}: n={n} hit={totals['hit'] / n:.1%} "
        f"recall={totals['recall'] / n:.3f} "
        f"precision={totals['precision'] / n:.3f} mrr={totals['mrr'] / n:.3f}"
    )


def _graph_stats(db: LatticeDB) -> dict:
    g = db.graph.graph
    node_counts = dict(Counter(d.get("type", "unknown") for _, d in g.nodes(data=True)))
    edge_counts = dict(Counter(d.get("type", "unknown") for _, _, d in g.edges(data=True)))
    return {
        "nodes_total": g.number_of_nodes(),
        "edges_total": g.number_of_edges(),
        "nodes_by_type": node_counts,
        "edges_by_type": edge_counts,
    }


def _ingest_summary(db: LatticeDB) -> dict:
    all_atoms = db.all()
    kinds = dict(Counter(a.kind for a in all_atoms))
    superseded = sum(1 for a in all_atoms if a.is_superseded)
    return {"atoms_by_kind": kinds, "superseded_count": superseded}


def _valid_as_of(atom, as_of: date | None) -> bool:
    if atom.is_superseded:
        return False
    if as_of is None:
        return True
    return (atom.valid_from is None or atom.valid_from <= as_of) and (
        atom.valid_until is None or atom.valid_until >= as_of
    )


def _unload_models(cfg: dict) -> None:
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    models = {cfg["llm_model"]}
    synthesis_model = os.environ.get("SYNTHESIS_MODEL")
    if synthesis_model:
        models.add(synthesis_model)
    for m in models:
        requests.post(f"{ollama_host}/api/generate", json={"model": m, "keep_alive": 0})
        print(f"Unloaded {m} from GPU.")


# ── phase 1: ingest ───────────────────────────────────────────────────────────


def _run_ingest(cfg: dict) -> None:
    """Ingest all questions into per-question lattice dirs. Resumable."""
    out_path = Path(cfg["out"])
    lattice_root = out_path.with_suffix("").with_name(out_path.stem + ".lattices")
    lattice_root.mkdir(parents=True, exist_ok=True)

    os.environ["LLM_PROVIDER"] = cfg["llm_provider"]
    os.environ["LLM_MODEL"] = cfg["llm_model"]

    print(f"Loading dataset: {cfg['dataset']}")
    with open(cfg["dataset"]) as f:
        data = json.load(f)

    sample = _stratify(data, cfg["stratify"], cfg["seed"])
    type_counts = Counter(q["question_type"] for q in sample)
    print(f"Stratified sample: {len(sample)} questions")
    for qtype, count in sorted(type_counts.items()):
        print(f"  {qtype}: {count}")
    print(f"Lattice root: {lattice_root}")
    print()

    n_done = n_skip = 0
    atoms_total = 0

    with tqdm(total=len(sample), unit="q") as pbar:
        for item in sample:
            qid = item["question_id"]
            qtype = item["question_type"]
            pbar.set_description(qtype[:24])

            tmpdir = str(lattice_root / qid)
            db_check = LatticeDB(lattice_dir=tmpdir)
            if Path(tmpdir).exists() and db_check.all():
                n_skip += 1
                pbar.update(1)
                continue

            shutil.rmtree(tmpdir, ignore_errors=True)
            Path(tmpdir).mkdir(parents=True, exist_ok=True)
            db = LatticeDB(lattice_dir=tmpdir)

            sessions = item.get("haystack_sessions", [])
            session_ids = item.get("haystack_session_ids", [f"s{i}" for i in range(len(sessions))])
            dates = item.get("haystack_dates", ["" for _ in sessions])

            atoms_created = 0
            for session, sid, ts in zip(sessions, session_ids, dates):
                text = format_session(session, sid, ts)
                result = ingest(
                    text,
                    metadata={"source": "conversation", "date": ts, "session_id": sid},
                    db=db,
                )
                atoms_created += result["atoms_created"]

            atoms_total += atoms_created
            n_done += 1
            pbar.update(1)

    print(f"\nIngest complete: {n_done} ingested, {n_skip} skipped (resumable)")
    print(f"Total atoms: {atoms_total}  |  Avg per question: {atoms_total / max(n_done, 1):.1f}")
    print(f"\nNext — run inference:")
    print(f"  python -m lattice.eval.run_eval --phase inference --priority {cfg['priority'] or '<priority>'} \\")
    print(f"    --reuse-lattice-root {lattice_root}")

    _unload_models(cfg)


# ── phase 2: inference (select + synthesize) ──────────────────────────────────


def _run_inference(cfg: dict) -> None:
    """Select + synthesize over pre-ingested lattice dirs. Requires --reuse-lattice-root."""
    reuse_lattice_root = Path(cfg["reuse_lattice_root"])
    if not reuse_lattice_root.exists():
        sys.exit(f"ERROR: lattice root not found: {reuse_lattice_root}\nRun --phase ingest first.")

    out_path = Path(cfg["out"])
    debug_path = out_path.with_name(out_path.stem + ".debug.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    os.environ["LLM_PROVIDER"] = cfg["llm_provider"]
    os.environ["LLM_MODEL"] = cfg["llm_model"]

    print(f"Loading dataset: {cfg['dataset']}")
    with open(cfg["dataset"]) as f:
        data = json.load(f)

    sample = _stratify(data, cfg["stratify"], cfg["seed"])
    done_ids = _load_done_ids(out_path)

    type_counts = Counter(q["question_type"] for q in sample)
    print(f"Stratified sample: {len(sample)} questions")
    for qtype, count in sorted(type_counts.items()):
        print(f"  {qtype}: {count}")
    print(f"Already done: {len(done_ids)} — will skip")

    n_done = n_err = 0
    atoms_selected_total = bm25_candidates_total = 0
    bm25_retrieval_totals = _new_retrieval_totals()
    selected_retrieval_totals = _new_retrieval_totals()

    with (
        out_path.open("a") as out_f,
        debug_path.open("a") as dbg_f,
        tqdm(total=len(sample) - len(done_ids), unit="q") as pbar,
    ):
        for item in sample:
            qid = item["question_id"]
            if qid in done_ids:
                continue

            qtype = item["question_type"]
            pbar.set_description(qtype[:24])

            lattice_dir = str(reuse_lattice_root / qid)
            if not Path(lattice_dir).exists():
                out_f.write(json.dumps({"question_id": qid, "hypothesis": f"ERROR: missing lattice dir"}) + "\n")
                out_f.flush()
                n_err += 1
                pbar.update(1)
                continue

            try:
                db = LatticeDB(lattice_dir=lattice_dir)
                db.preload()

                question_date_str: str | None = item.get("question_date")
                as_of: date | None = None
                if question_date_str:
                    dt = _parse_datetime(question_date_str)
                    if dt:
                        as_of = dt.date()

                bm25_atoms = db.search(item["question"], as_of=as_of, top_k=cfg["top_k"])
                bm25_candidates = [_atom_debug_dict(atom, preview_chars=240) for atom in bm25_atoms]

                selection_tool_calls: list[dict] = []
                if cfg["retrieval_mode"] == "select":
                    selected = select(item["question"], as_of=as_of, db=db, top_k=cfg["top_k"])
                elif cfg["retrieval_mode"] == "agent":
                    agent_result = select_agent(item["question"], as_of=as_of, db=db, top_k=cfg["top_k"])
                    selected = agent_result.atoms
                    selection_tool_calls = agent_result.agent_tool_calls
                elif cfg["retrieval_mode"] == "bm25":
                    selected = [_atom_debug_dict(atom) for atom in bm25_atoms]
                else:
                    selected = [_atom_debug_dict(atom) for atom in db.all() if _valid_as_of(atom, as_of)]

                retrieval_oracle = {
                    "bm25": _session_retrieval_metrics(item, bm25_candidates),
                    "selected": _session_retrieval_metrics(item, selected),
                }
                answer_token_recall = _answer_token_recall(item.get("answer", ""), selected)
                synthesis = synthesize(item["question"], selected, query_date=as_of)

                all_atoms = [_atom_debug_dict(a, preview_chars=240) for a in db.all()]
                ingest_summary = _ingest_summary(db)
                session_hit = retrieval_oracle["selected"].get("session_hit", False)
                atom_count_total = len(db.all())
                atom_count_active = atom_count_total - ingest_summary["superseded_count"]

                out_f.write(json.dumps({"question_id": qid, "hypothesis": synthesis.answer}) + "\n")
                out_f.flush()

                dbg_f.write(json.dumps({
                    "question_id": qid,
                    "question": item["question"],
                    "gold_answer": item.get("answer", ""),
                    "question_type": qtype,
                    "session_hit": session_hit,
                    "lattice_dir": lattice_dir,
                    "reuse_lattice_root": str(reuse_lattice_root),
                    "sessions_ingested": len(item.get("haystack_sessions", [])),
                    "retrieval_mode": cfg["retrieval_mode"],
                    "top_k": cfg["top_k"],
                    "atom_count_total": atom_count_total,
                    "atom_count_active": atom_count_active,
                    "atoms_by_kind": ingest_summary["atoms_by_kind"],
                    "superseded_count": ingest_summary["superseded_count"],
                    "atoms": all_atoms,
                    "answer_oracle": _answer_turn_summary(item),
                    "retrieval_oracle": retrieval_oracle,
                    "answer_token_recall": answer_token_recall,
                    "bm25_candidates": bm25_candidates,
                    "selected_atoms": selected,
                    "selection_tool_calls": selection_tool_calls,
                    "synthesis_raw": synthesis.raw_response,
                    "synthesis_tool_calls": synthesis.tool_calls,
                    "hypothesis": synthesis.answer,
                    "graph_stats": _graph_stats(db),
                }) + "\n")
                dbg_f.flush()

                atoms_selected_total += len(selected)
                bm25_candidates_total += len(bm25_candidates)
                _add_retrieval_totals(bm25_retrieval_totals, retrieval_oracle["bm25"])
                _add_retrieval_totals(selected_retrieval_totals, retrieval_oracle["selected"])
                n_done += 1

            except Exception as exc:
                out_f.write(json.dumps({"question_id": qid, "hypothesis": f"ERROR: {exc}"}) + "\n")
                out_f.flush()
                n_err += 1

            pbar.update(1)

    print("\n── Inference summary ──────────────────────────────────────────")
    print(f"  Processed : {n_done}")
    print(f"  Errors    : {n_err}")
    print(f"  Retrieval : {cfg['retrieval_mode']} (top_k={cfg['top_k']})")
    print(f"  Reuse DBs : {reuse_lattice_root}")
    if n_done:
        print(f"  Avg BM25 candidates: {bm25_candidates_total / n_done:.1f}")
        print(f"  Avg atoms selected : {atoms_selected_total / n_done:.1f}")
        print("  Session oracle:")
        print(_format_retrieval_totals("BM25", bm25_retrieval_totals))
        print(_format_retrieval_totals("Selected", selected_retrieval_totals))
    print(f"  Results   : {out_path}")
    print(f"  Debug     : {debug_path}")

    _unload_models(cfg)


# ── replay inference (synthesis-only over debug atoms) ───────────────────────


def _run_replay_inference(cfg: dict) -> None:
    """Re-run synthesis over atoms from a prior debug file. Skips ingest + selection."""
    replay_path = Path(cfg["replay_debug"])
    if not replay_path.exists():
        sys.exit(f"ERROR: replay debug file not found: {replay_path}")

    out_path = Path(cfg["out"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    debug_path = out_path.with_name(out_path.stem + ".debug.jsonl")

    print(f"Loading dataset: {cfg['dataset']}")
    with open(cfg["dataset"]) as f:
        data = json.load(f)
    dataset_by_id = {item["question_id"]: item for item in data}

    print(f"Loading replay debug: {replay_path}")
    replay_by_id: dict[str, dict] = {}
    with replay_path.open() as f:
        for line in f:
            r = json.loads(line)
            replay_by_id[r["question_id"]] = r

    os.environ["LLM_PROVIDER"] = cfg["llm_provider"]
    os.environ["LLM_MODEL"] = cfg["llm_model"]

    done_ids = _load_done_ids(out_path)
    rerank = cfg["replay_rerank"]
    print(f"Questions in debug: {len(replay_by_id)}, already done: {len(done_ids)}")

    n_done = n_err = 0
    atoms_selected_total = 0
    token_recall_total = 0.0

    with (
        out_path.open("a") as out_f,
        debug_path.open("a") as dbg_f,
        tqdm(total=len(replay_by_id) - len(done_ids), unit="q") as pbar,
    ):
        for qid, replay in replay_by_id.items():
            if qid in done_ids:
                continue

            qtype = replay.get("question_type", "?")
            pbar.set_description(qtype[:24])

            try:
                item = dataset_by_id.get(qid, {})
                question = replay.get("question") or item.get("question", "")
                atoms = replay.get("selected_atoms", replay.get("atoms", []))

                question_date_str: str | None = item.get("question_date")
                as_of: date | None = None
                if question_date_str:
                    dt = _parse_datetime(question_date_str)
                    if dt:
                        as_of = dt.date()

                if rerank:
                    atoms = rerank_atom_dicts(question, atoms)

                gold_answer = replay.get("gold_answer") or item.get("answer", "")
                answer_token_recall = _answer_token_recall(gold_answer, atoms)
                synthesis = synthesize(question, atoms, query_date=as_of)

                out_f.write(json.dumps({"question_id": qid, "hypothesis": synthesis.answer}) + "\n")
                out_f.flush()

                dbg_f.write(json.dumps({
                    "question_id": qid,
                    "question": question,
                    "gold_answer": gold_answer,
                    "question_type": qtype,
                    "replay_source": str(replay_path),
                    "replay_rerank": rerank,
                    "atoms_replayed": len(atoms),
                    "selected_atoms": atoms,
                    "answer_token_recall": answer_token_recall,
                    "synthesis_raw": synthesis.raw_response,
                    "synthesis_tool_calls": synthesis.tool_calls,
                    "hypothesis": synthesis.answer,
                }) + "\n")
                dbg_f.flush()

                atoms_selected_total += len(atoms)
                token_recall_total += answer_token_recall
                n_done += 1

            except Exception as exc:
                out_f.write(json.dumps({"question_id": qid, "hypothesis": f"ERROR: {exc}"}) + "\n")
                out_f.flush()
                n_err += 1

            pbar.update(1)

    print("\n── Replay inference summary ───────────────────────────────────")
    print(f"  Processed : {n_done}")
    print(f"  Errors    : {n_err}")
    if n_done:
        print(f"  Avg atoms replayed     : {atoms_selected_total / n_done:.1f}")
        print(f"  Avg answer token recall: {token_recall_total / n_done:.3f}")
    print(f"  Results   : {out_path}")
    print(f"  Debug     : {debug_path}")

    _unload_models(cfg)


# ── phase 3: judge ────────────────────────────────────────────────────────────


def _wait_for_proxy(port: int, timeout: int = 30) -> None:
    url = f"http://localhost:{port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(url, timeout=2).status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"LiteLLM proxy did not start within {timeout}s")


def _ensure_model_pulled(model: str) -> None:
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if model not in result.stdout:
        print(f"Pulling judge model: {model}")
        subprocess.run(["ollama", "pull", model], check=True)


def _run_judge(cfg: dict) -> None:
    out_path = Path(cfg["out"])
    if not out_path.exists():
        sys.exit(f"ERROR: Results file not found: {out_path}. Run --phase inference first.")

    evaluate_script = cfg["evaluate_script"]
    if not evaluate_script:
        sys.exit("ERROR: EVALUATE_SCRIPT not set. Add path to evaluate_qa.py in .env.eval.")

    judge_model = cfg["judge_model"]
    _ensure_model_pulled(judge_model)

    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    env = {**os.environ, "OLLAMA_BASE_URL": f"{ollama_host}/v1"}

    result_file = str(out_path) + f".eval-results-{judge_model}"
    print(f"Running evaluate_qa.py with judge model: {judge_model}")
    subprocess.run(
        [sys.executable, evaluate_script, judge_model, str(out_path), cfg["dataset"]],
        env=env,
        check=True,
    )

    if Path(result_file).exists():
        print("\n── Scoring summary ────────────────────────────────────────────")
        if cfg["print_qa_script"]:
            out = subprocess.run(
                [sys.executable, cfg["print_qa_script"], result_file, cfg["dataset"]],
                capture_output=True,
                text=True,
            )
            if out.stdout:
                print(out.stdout, end="")
            if out.stderr:
                print(out.stderr, end="", file=sys.stderr)

    requests.post(f"{ollama_host}/api/generate", json={"model": judge_model, "keep_alive": 0})
    print(f"Unloaded {judge_model} from GPU.")


# ── entrypoint ─────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LongMemEval harness for lattice-mcp")
    p.add_argument("--phase", choices=["ingest", "inference", "judge"], required=True,
                   help="ingest: extract atoms from sessions; inference: select+synthesize; judge: score")
    p.add_argument("--priority", default="", help="Iteration label, e.g. p18")
    p.add_argument("--dataset", default="")
    p.add_argument("--out", default="", help="Override inference results file path")
    p.add_argument("--log", default="", help="Override log file path")
    p.add_argument("--stratify", type=int, default=0)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--retrieval-mode", choices=["select", "bm25", "all", "agent"], default="",
                   help="select=BM25+graph+LLM (default), bm25=BM25 only, all=no retrieval")
    p.add_argument("--top-k", type=int, default=0, help="BM25 candidate count (default 20)")
    p.add_argument("--evaluate-script", default="")
    p.add_argument("--print-qa-script", default="")
    p.add_argument("--reuse-lattice-root", default="",
                   help="Path to lattice dirs from --phase ingest. Required for --phase inference.")
    p.add_argument("--replay-debug", default="",
                   help="Path to a prior .debug.jsonl. Skips ingest+selection; re-runs synthesis only.")
    p.add_argument("--replay-rerank", action="store_true",
                   help="Re-rank atoms by embedding similarity before replay synthesis.")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    cfg = _load_config(args)

    log_path = Path(cfg["log"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(log_path, "w", buffering=1)
    sys.stdout = _Tee(sys.__stdout__, log_f)
    sys.stderr = _Tee(sys.__stderr__, log_f)

    try:
        print(f"Priority : {cfg['priority'] or '(none)'}")
        print(f"Phase    : {args.phase}")
        print(f"LLM      : {cfg['llm_model']}")
        if cfg.get("ingest_model"):
            print(f"Ingest   : {cfg['ingest_model']}")
        print(f"Judge    : {cfg['judge_model']}")
        print(f"Dataset  : {Path(cfg['dataset']).stem}")
        print(f"Retrieve : {cfg['retrieval_mode']} (top_k={cfg['top_k']})")
        print(f"Reuse DBs: {cfg['reuse_lattice_root'] or '(none)'}")
        print(f"Out      : {cfg['out']}")
        print(f"Log      : {log_path}")
        print()

        if args.phase == "ingest":
            _run_ingest(cfg)
        elif args.phase == "inference":
            if cfg["replay_debug"]:
                _run_replay_inference(cfg)
            elif not cfg["reuse_lattice_root"]:
                sys.exit(
                    "ERROR: --phase inference requires --reuse-lattice-root.\n"
                    "Run --phase ingest first to build lattice dirs."
                )
            else:
                _run_inference(cfg)
        elif args.phase == "judge":
            _run_judge(cfg)
    finally:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        log_f.close()


if __name__ == "__main__":
    main()
