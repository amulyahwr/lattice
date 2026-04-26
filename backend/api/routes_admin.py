"""Admin and audit routes — stats, activity, access logs.

Evolved from routes_graph.py. Provides dashboard stats, activity feed,
and audit log for the frontend.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.compiler.linker import cross_link_atoms
from backend.compiler.pipeline import fetch_cross_link_candidates
from backend.models.atoms import AccessLog, AgentProfile, Atom, AtomSource, Source
from backend.models.database import get_db

router = APIRouter(tags=["admin"])


# ── Cross-source Relink ──


class RelinkResponse(BaseModel):
    sources_processed: int
    cross_links_added: int


@router.post("/admin/relink", response_model=RelinkResponse)
async def admin_relink(db: AsyncSession = Depends(get_db)):
    """Re-run cross-source linking across all existing atoms.

    For each source, treats its atoms as "new" and fetches domain-aware
    candidates from all other sources. Appends cross-links without
    overwriting existing within-source links.
    """
    sources_result = await db.execute(select(Source))
    sources = sources_result.scalars().all()

    total_links_added = 0
    sources_processed = 0

    for source in sources:
        atoms_result = await db.execute(
            select(Atom)
            .join(AtomSource, Atom.id == AtomSource.atom_id)
            .where(AtomSource.source_id == source.id)
        )
        source_atoms = [a for a in atoms_result.scalars().all() if a.dense_vec is not None]

        if not source_atoms:
            continue

        candidates = await fetch_cross_link_candidates(
            db=db,
            new_atom_ids=[a.id for a in source_atoms],
            new_embeddings=[a.dense_vec for a in source_atoms],
            new_domains=[a.domain or [] for a in source_atoms],
        )

        if candidates:
            cl_sets = await cross_link_atoms(
                new_contents=[a.content for a in source_atoms],
                existing_contents=[c.content for c in candidates],
            )

            for atom, atom_cl in zip(source_atoms, cl_sets):
                existing_targets = {lnk["target_id"] for lnk in (atom.links or [])}
                for cl in atom_cl:
                    target_id = str(candidates[cl["existing_index"]].id)
                    if target_id not in existing_targets:
                        atom.links = (atom.links or []) + [
                            {"target_id": target_id, "relation": cl["relation"]}
                        ]
                        existing_targets.add(target_id)
                        total_links_added += 1

        sources_processed += 1

    await db.flush()

    return RelinkResponse(
        sources_processed=sources_processed,
        cross_links_added=total_links_added,
    )


# ── Admin Stats ──


class AdminStatsResponse(BaseModel):
    total_atoms: int
    total_agents: int
    total_sources: int
    atoms_by_kind: dict[str, int] = {}
    total_queries: int = 0


@router.get("/admin/stats", response_model=AdminStatsResponse)
async def admin_stats(db: AsyncSession = Depends(get_db)):
    """High-level system stats for dashboard."""
    atom_count = (await db.execute(select(func.count(Atom.id)))).scalar() or 0
    agent_count = (await db.execute(select(func.count(AgentProfile.id)))).scalar() or 0
    source_count = (await db.execute(select(func.count(Source.id)))).scalar() or 0

    # Atoms by kind
    kind_result = await db.execute(
        select(Atom.kind, func.count(Atom.id)).group_by(Atom.kind)
    )
    atoms_by_kind = {row[0]: row[1] for row in kind_result.fetchall()}

    # Total queries from access log
    query_count = (await db.execute(select(func.count(AccessLog.id)))).scalar() or 0

    return AdminStatsResponse(
        total_atoms=atom_count,
        total_agents=agent_count,
        total_sources=source_count,
        atoms_by_kind=atoms_by_kind,
        total_queries=query_count,
    )


# ── Activity Feed ──


class ActivityEvent(BaseModel):
    type: str  # "query" | "ingest" | "access"
    agent_name: str | None = None
    query: str | None = None
    decision: str | None = None
    atoms_served: int | None = None
    cache_tier: str | None = None
    latency_ms: float | None = None
    timestamp: str | None = None


class ActivityResponse(BaseModel):
    events: list[ActivityEvent]
    total: int


@router.get("/admin/activity", response_model=ActivityResponse)
async def admin_activity(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Recent activity: queries, compilations, access events."""
    result = await db.execute(
        select(AccessLog, AgentProfile.name.label("agent_name"))
        .join(AgentProfile, AccessLog.agent_id == AgentProfile.id, isouter=True)
        .order_by(AccessLog.timestamp.desc())
        .limit(limit)
    )
    rows = result.fetchall()

    events = []
    for row in rows:
        log = row[0]
        agent_name = row.agent_name
        events.append(
            ActivityEvent(
                type="query",
                agent_name=agent_name,
                query=log.query,
                decision=log.decision,
                atoms_served=log.atoms_served,
                cache_tier=log.cache_tier,
                latency_ms=log.latency_ms,
                timestamp=log.timestamp.isoformat() if log.timestamp else None,
            )
        )

    total = (await db.execute(select(func.count(AccessLog.id)))).scalar() or 0

    return ActivityResponse(events=events, total=total)


# ── Audit Log ──


class AuditLogEntry(BaseModel):
    id: str
    agent_name: str | None = None
    query: str | None = None
    decision: str
    atoms_served: int = 0
    atoms_filtered: int = 0
    cache_tier: str | None = None
    latency_ms: float | None = None
    timestamp: str | None = None


class AuditLogResponse(BaseModel):
    entries: list[AuditLogEntry]
    total: int
    page: int
    page_size: int


@router.get("/audit/log", response_model=AuditLogResponse)
async def audit_log(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    agent_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Paginated access log for audit."""
    offset = (page - 1) * page_size

    query = (
        select(AccessLog, AgentProfile.name.label("agent_name"))
        .join(AgentProfile, AccessLog.agent_id == AgentProfile.id, isouter=True)
        .order_by(AccessLog.timestamp.desc())
    )

    count_query = select(func.count(AccessLog.id))

    if agent_id:
        agent_uuid = uuid.UUID(agent_id)
        query = query.where(AccessLog.agent_id == agent_uuid)
        count_query = count_query.where(AccessLog.agent_id == agent_uuid)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.limit(page_size).offset(offset))
    rows = result.fetchall()

    entries = []
    for row in rows:
        log = row[0]
        entries.append(
            AuditLogEntry(
                id=str(log.id),
                agent_name=row.agent_name,
                query=log.query,
                decision=log.decision,
                atoms_served=log.atoms_served or 0,
                atoms_filtered=log.atoms_filtered or 0,
                cache_tier=log.cache_tier,
                latency_ms=log.latency_ms,
                timestamp=log.timestamp.isoformat() if log.timestamp else None,
            )
        )

    return AuditLogResponse(
        entries=entries,
        total=total,
        page=page,
        page_size=page_size,
    )


# ── Audit Stats ──


class AuditStatsResponse(BaseModel):
    total_queries: int
    total_granted: int
    total_denied: int
    total_filtered: int
    denied_by_agent: dict[str, int] = {}


@router.get("/audit/stats", response_model=AuditStatsResponse)
async def audit_stats(db: AsyncSession = Depends(get_db)):
    """Access denied breakdown for audit dashboard."""
    total = (await db.execute(select(func.count(AccessLog.id)))).scalar() or 0

    granted = (
        await db.execute(
            select(func.count(AccessLog.id)).where(AccessLog.decision == "granted")
        )
    ).scalar() or 0

    denied = (
        await db.execute(
            select(func.count(AccessLog.id)).where(AccessLog.decision == "denied")
        )
    ).scalar() or 0

    filtered = (
        await db.execute(
            select(func.count(AccessLog.id)).where(AccessLog.decision == "filtered")
        )
    ).scalar() or 0

    # Denied breakdown by agent
    denied_by = await db.execute(
        select(AgentProfile.name, func.count(AccessLog.id))
        .join(AgentProfile, AccessLog.agent_id == AgentProfile.id)
        .where(AccessLog.decision == "denied")
        .group_by(AgentProfile.name)
    )
    denied_by_agent = {row[0]: row[1] for row in denied_by.fetchall()}

    return AuditStatsResponse(
        total_queries=total,
        total_granted=granted,
        total_denied=denied,
        total_filtered=filtered,
        denied_by_agent=denied_by_agent,
    )
