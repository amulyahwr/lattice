"""L3 Search — multi-hypothesis pgvector search with RRF fusion.

Search flow:
  1. Embed each hypothesis independently.
  2. Optional canonical pre-filter narrows the atom pool before cosine search.
  3. RRF (Reciprocal Rank Fusion) merges per-hypothesis ranked lists into one shortlist,
     deduplicating by atom_id and surfacing atoms that appear across multiple hypotheses.
  4. Final score = best_cosine_sim × confidence_weight × freshness_weight.
  5. Optional LLM re-ranker as a second pass (deep_rerank=True).
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, literal, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.compiler.llm_client import chat
from backend.compiler.query_processor import normalize_period
from backend.engine.embeddings import embed_text
from backend.models.atoms import Atom, AtomSource, Source

logger = logging.getLogger(__name__)

# ── Re-ranking constants ──────────────────────────────────────────────────────

_FRESHNESS_LAMBDA = 0.005   # exp decay half-life ≈ 139 days
_CONFIDENCE_CAP = 3.0       # consolidator caps meaningful range around here
_RRF_K = 60                 # standard RRF smoothing constant


# ── Score helpers ─────────────────────────────────────────────────────────────


def _confidence_weight(confidence: float) -> float:
    # log curve: 1.0→1.0x, 2.0→1.17x, 3.0→1.27x
    return 1.0 + math.log(min(confidence or 1.0, _CONFIDENCE_CAP)) / 4.0


def _freshness_weight(freshness: datetime | None) -> float:
    if freshness is None:
        return 1.0
    if freshness.tzinfo is None:
        freshness = freshness.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - freshness).total_seconds() / 86400
    return math.exp(-_FRESHNESS_LAMBDA * max(age_days, 0.0))


# ── RRF fusion ────────────────────────────────────────────────────────────────


def _rrf_fuse(ranked_lists: list[list[Any]]) -> list[Any]:
    """Merge ranked row lists via Reciprocal Rank Fusion.

    Atoms appearing in multiple hypothesis shortlists accumulate score. For each
    atom, the row with the best (lowest) cosine distance is kept so that the
    final heuristic score uses the strongest semantic match.
    """
    rrf_scores: dict[str, float] = {}
    best_row: dict[str, Any] = {}

    for ranked in ranked_lists:
        for rank, row in enumerate(ranked):
            aid = str(row.id)
            rrf_scores[aid] = rrf_scores.get(aid, 0.0) + 1.0 / (_RRF_K + rank + 1)
            if aid not in best_row or row.distance < best_row[aid].distance:
                best_row[aid] = row

    ordered = sorted(rrf_scores, key=lambda aid: rrf_scores[aid], reverse=True)
    return [best_row[aid] for aid in ordered]


# ── LLM re-ranker (optional deep pass) ───────────────────────────────────────


class _RankedItem(BaseModel):
    index: int
    score: int  # 1–10


class _RerankerResponse(BaseModel):
    rankings: list[_RankedItem]


_RERANKER_SYSTEM = """\
You are a search result re-ranker for a knowledge base.
Given a user query and a numbered list of candidate atoms, score each candidate \
from 1 (irrelevant) to 10 (perfectly relevant) based solely on relevance to the query.
Return a JSON object with a "rankings" list, each entry having "index" (integer) \
and "score" (integer 1–10). Include every candidate index."""


async def _llm_rerank(raw_query: str, candidates: list[dict]) -> list[dict]:
    """Re-rank candidates with an LLM call. Falls back to input order on any error."""
    if not candidates:
        return candidates
    try:
        items = "\n".join(
            f"{i}: [{c['kind']}] {c['content'][:160]}"
            for i, c in enumerate(candidates)
        )
        payload = f"Query: {raw_query}\n\nCandidates:\n{items}"
        raw = await chat(_RERANKER_SYSTEM, payload, response_format=_RerankerResponse, temperature=0.0)
        start, end = raw.find("{"), raw.rfind("}")
        parsed = _RerankerResponse.model_validate_json(raw[start : end + 1])
        score_map = {r.index: r.score for r in parsed.rankings}
        return sorted(candidates, key=lambda c: -score_map.get(candidates.index(c), 0))
    except Exception as exc:
        logger.warning("_llm_rerank failed: %s", exc)
        return candidates


# ── Core search ───────────────────────────────────────────────────────────────


async def _search_one(
    db: AsyncSession,
    embedding: list[float],
    role_mask: int,
    top_k: int,
    domain_filter: list[str] | None,
    period_filter: str | None,
    primary_source: Any,
) -> list[Any]:
    """Run a single pgvector query and return raw rows ordered by cosine distance."""
    stmt = (
        select(
            Atom.id,
            Atom.content,
            Atom.raw_content,
            Atom.kind,
            Atom.domain,
            Atom.confidence,
            Atom.access_mask,
            Atom.links,
            Atom.freshness,
            Atom.version,
            Atom.canonical,
            primary_source.c.name.label("source_name"),
            primary_source.c.source_type,
            Atom.dense_vec.cosine_distance(embedding).label("distance"),
        )
        .outerjoin(primary_source, Atom.id == primary_source.c.atom_id)
        .where(Atom.access_mask.bitwise_and(role_mask) != 0)
        .where(Atom.is_superseded.is_(False))
        .order_by("distance")
        .limit(top_k)
    )

    if domain_filter:
        stmt = stmt.where(Atom.domain.overlap(domain_filter))

    if period_filter:
        # Bidirectional substring match — "Q2" matches "Q2 2024" and vice versa.
        # Atoms with no canonical_period (events, decisions) always pass through.
        period_norm = (normalize_period(period_filter) or period_filter).lower()
        stmt = stmt.where(
            or_(
                func.lower(Atom.canonical_period).contains(period_norm),
                literal(period_norm).ilike(func.concat("%", func.lower(Atom.canonical_period), "%")),
                Atom.canonical_period.is_(None),
            )
        )

    result = await db.execute(stmt)
    return result.fetchall()


async def _search_bm25(
    db: AsyncSession,
    query_text: str,
    role_mask: int,
    top_k: int,
    domain_filter: list[str] | None,
    primary_source: Any,
) -> list[Any]:
    """Full-text BM25 search via PostgreSQL tsvector/tsquery.

    Catches exact term, ID, and name matches that dense vectors miss.
    Results feed into the same RRF fusion as hypothesis embeddings so atoms
    appearing in both BM25 and dense lists get a double boost.

    Note: a GIN index on to_tsvector('english', content) is recommended for
    production performance on large atom stores.
    """
    tsquery = func.plainto_tsquery(text("'english'"), query_text)
    tsvector = func.to_tsvector(text("'english'"), Atom.content)
    rank = func.ts_rank_cd(tsvector, tsquery)

    stmt = (
        select(
            Atom.id,
            Atom.content,
            Atom.raw_content,
            Atom.kind,
            Atom.domain,
            Atom.confidence,
            Atom.access_mask,
            Atom.links,
            Atom.freshness,
            Atom.version,
            Atom.canonical,
            primary_source.c.name.label("source_name"),
            primary_source.c.source_type,
            (literal(1.0) - func.least(literal(1.0), rank)).label("distance"),
        )
        .outerjoin(primary_source, Atom.id == primary_source.c.atom_id)
        .where(Atom.access_mask.bitwise_and(role_mask) != 0)
        .where(Atom.is_superseded.is_(False))
        .where(tsvector.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(top_k)
    )

    if domain_filter:
        stmt = stmt.where(Atom.domain.overlap(domain_filter))

    result = await db.execute(stmt)
    return result.fetchall()


async def search_atoms(
    db: AsyncSession,
    hypotheses: list[str],
    role_mask: int,
    top_k: int = 20,
    domain_filter: list[str] | None = None,
    min_relevance: float = 0.0,
    query_canonical: dict | None = None,
    deep_rerank: bool = False,
    raw_query: str | None = None,
) -> list[dict]:
    """Search atoms via multi-hypothesis embedding + RRF fusion.

    Each hypothesis is embedded and queried independently against pgvector.
    Results are merged with Reciprocal Rank Fusion, then re-scored by
    confidence × freshness. Optionally a second LLM pass re-ranks the shortlist.

    Args:
        hypotheses:      List of declarative statements to embed (from process_query).
        query_canonical: Extracted {subject, period} for pre-filtering and boosting.
        deep_rerank:     If True, calls the LLM re-ranker on the final shortlist.
        raw_query:       Original user query, passed to the LLM re-ranker prompt.
    """
    period_filter: str | None = (query_canonical or {}).get("period")

    primary_source = (
        select(AtomSource.atom_id, Source.name, Source.source_type)
        .join(Source, AtomSource.source_id == Source.id)
        .where(AtomSource.is_primary.is_(True))
        .subquery()
    )

    # ── Per-hypothesis dense searches (sequential — single session constraint) ─
    all_ranked: list[list[Any]] = []
    for hypothesis in hypotheses:
        embedding = embed_text(hypothesis)
        rows = await _search_one(db, embedding, role_mask, top_k, domain_filter, period_filter, primary_source)
        if rows:
            all_ranked.append(list(rows))

    # ── BM25 full-text search (fused as an additional ranked list) ────────────
    if raw_query:
        bm25_rows = await _search_bm25(db, raw_query, role_mask, top_k, domain_filter, primary_source)
        if bm25_rows:
            all_ranked.append(list(bm25_rows))

    if not all_ranked:
        return []

    # ── RRF fusion ────────────────────────────────────────────────────────────
    fused = _rrf_fuse(all_ranked)

    # ── Heuristic re-scoring (confidence × freshness on best-matching row) ────
    candidates: list[dict] = []
    for row in fused:
        cosine_sim = round(1 - row.distance, 4)
        final_score = (
            cosine_sim
            * _confidence_weight(row.confidence)
            * _freshness_weight(row.freshness)
        )
        final_score = min(1.0, max(0.0, final_score))
        if final_score < min_relevance:
            continue
        candidates.append({
            "atom_id": str(row.id),
            "content": row.content,
            "raw_content": row.raw_content,
            "kind": row.kind,
            "domain": row.domain or [],
            "confidence": row.confidence,
            "access_mask": row.access_mask,
            "links": row.links or [],
            "source_name": row.source_name,
            "source_type": row.source_type,
            "freshness": row.freshness.isoformat() if row.freshness else None,
            "version": row.version,
            "relevance_score": final_score,
            "canonical": row.canonical,
        })

    candidates.sort(key=lambda r: r["relevance_score"], reverse=True)

    # ── Optional LLM re-ranking ───────────────────────────────────────────────
    if deep_rerank and raw_query and candidates:
        candidates = await _llm_rerank(raw_query, candidates)

    return candidates


# ── Utility queries ───────────────────────────────────────────────────────────


async def count_atoms_by_source(db: AsyncSession, source_id) -> int:
    """Count atoms linked to a source via atom_sources."""
    from sqlalchemy import func
    result = await db.execute(
        select(func.count(AtomSource.atom_id)).where(AtomSource.source_id == source_id)
    )
    return result.scalar() or 0


async def get_atoms_by_source(
    db: AsyncSession,
    source_id,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Get atoms linked to a source via atom_sources."""
    result = await db.execute(
        select(Atom)
        .join(AtomSource, Atom.id == AtomSource.atom_id)
        .where(AtomSource.source_id == source_id)
        .order_by(Atom.compiled_at.desc())
        .limit(limit)
        .offset(offset)
    )
    atoms = result.scalars().all()

    return [
        {
            "atom_id": str(a.id),
            "content": a.content,
            "raw_content": a.raw_content,
            "kind": a.kind,
            "domain": a.domain or [],
            "confidence": a.confidence,
            "access_mask": a.access_mask,
            "links": a.links or [],
            "freshness": a.freshness.isoformat() if a.freshness else None,
            "version": a.version,
        }
        for a in atoms
    ]
