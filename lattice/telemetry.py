from __future__ import annotations

import json
from datetime import date, datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lattice.config import Config


def record_usage(
    query: str,
    sel_ms: int,
    syn_ms: int,
    n_atoms: int,
    channel: str,
    cfg: "Config",
) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "query_hash": sha1(query.encode()).hexdigest(),
        "selection_ms": sel_ms,
        "synthesis_ms": syn_ms,
        "atom_count": n_atoms,
        "channel": channel,
    }
    with (Path(cfg.lattice_dir) / "usage.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def load_usage(cfg: "Config") -> list[dict]:
    path = Path(cfg.lattice_dir) / "usage.jsonl"
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def record_grace_day(cfg: "Config") -> None:
    entry = json.dumps({"type": "grace_day_used", "ts": datetime.now(timezone.utc).isoformat()})
    with (Path(cfg.lattice_dir) / "usage.jsonl").open("a", encoding="utf-8") as f:
        f.write(entry + "\n")


def compute_streak(records: list[dict]) -> tuple[int, bool]:
    """Return (streak, grace_day_active).

    grace_day_active is True when the user has not queried today but did query
    yesterday — streak is held at yesterday's value for one day before resetting.
    One grace day is allowed per 7-day window; after use it is recorded as a
    {type: 'grace_day_used'} sentinel in usage.jsonl so we don't double-grant.
    """
    today = datetime.now(tz=timezone.utc).date()
    yesterday = date.fromordinal(today.toordinal() - 1)

    query_days: set[date] = set()
    grace_used_dates: set[date] = set()
    for r in records:
        try:
            d = date.fromisoformat(r["ts"][:10])
            if r.get("type") == "grace_day_used":
                grace_used_dates.add(d)
            else:
                query_days.add(d)
        except (KeyError, ValueError):
            pass

    # Normal streak from today
    if today in query_days:
        streak = 0
        current = today
        while current in query_days:
            streak += 1
            current = date.fromordinal(current.toordinal() - 1)
        return streak, False

    # Today has no queries — check grace day eligibility
    if yesterday in query_days:
        week_ago = date.fromordinal(today.toordinal() - 6)
        grace_used_recently = any(d >= week_ago for d in grace_used_dates)
        if not grace_used_recently:
            streak = 0
            current = yesterday
            while current in query_days:
                streak += 1
                current = date.fromordinal(current.toordinal() - 1)
            return streak, True

    return 0, False
