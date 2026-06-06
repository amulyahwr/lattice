"""lattice.cli: lc — one-liner capture from the terminal."""
from __future__ import annotations

import sys


def lc() -> None:
    if len(sys.argv) < 2:
        print("Usage: lc <text>", file=sys.stderr)
        print("       lc status", file=sys.stderr)
        print("Example: lc \"decided to use Postgres for the new service\"", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == "status":
        from pathlib import Path as _Path
        from lattice.config import Config
        from lattice.db import LatticeDB
        cfg = Config.from_env()
        db = LatticeDB(cfg.lattice_dir)
        active = [a for a in db.all() if not a.is_superseded]
        count = len(active)
        topics = list(dict.fromkeys(a.subject for a in active if a.subject))[:5]

        # Fetch streak from usage.jsonl directly (no daemon needed)
        import json as _json
        from datetime import date as _date, datetime as _dt, timezone as _tz
        usage_path = _Path(cfg.lattice_dir) / "usage.jsonl"
        query_days: set[_date] = set()
        if usage_path.exists():
            for line in usage_path.read_text(encoding="utf-8").splitlines():
                try:
                    r = _json.loads(line)
                    if r.get("type") != "grace_day_used":
                        query_days.add(_date.fromisoformat(r["ts"][:10]))
                except Exception:
                    pass
        today = _dt.now(_tz.utc).date()
        streak = 0
        current = today
        while current in query_days:
            streak += 1
            current = _date.fromordinal(current.toordinal() - 1)

        parts = [f"{count} memories"]
        if topics:
            parts.append(f"Topics: {', '.join(topics)}")
        if streak > 0:
            depth = "day deep" if streak == 1 else "days deep"
            parts.append(f"{streak} {depth}")
        print(" · ".join(parts))
        return

    text = " ".join(sys.argv[1:])

    from lattice.client import DaemonClient
    try:
        atom_ids = DaemonClient().ingest(text, source_id="lc")
    except (RuntimeError, OSError):
        print("Lattice daemon not running. Start with: lattice-daemon", file=sys.stderr)
        sys.exit(1)

    print(f"Saved. {len(atom_ids)} new thing{'s' if len(atom_ids) != 1 else ''} added to your memory.")

    # Topic depth check — notify once per subject when threshold crossed
    if atom_ids:
        import json as _json
        from pathlib import Path as _Path
        from lattice.config import Config as _Config
        from lattice.db import LatticeDB as _LatticeDB
        import urllib.request as _ur
        try:
            cfg = _Config.from_env()
            db = _LatticeDB(cfg.lattice_dir)
            notified_path = _Path(cfg.lattice_dir) / "notified_depths.json"
            notified: dict = _json.loads(notified_path.read_text()) if notified_path.exists() else {}
            port = "7337"
            for aid in atom_ids:
                try:
                    atom = db.read(aid)
                    subject = atom.subject
                    if not subject or subject.lower().strip() in notified:
                        continue
                    with _ur.urlopen(f"http://127.0.0.1:{port}/api/topic/depth?subject={subject}", timeout=3) as r:
                        count = _json.loads(r.read()).get("count", 0)
                    for threshold, label in [(20, "This is one of the things you know best."), (10, "You've thought about this a lot."), (5, "That's a topic you know well.")]:
                        if count >= threshold:
                            notified[subject.lower().strip()] = threshold
                            notified_path.write_text(_json.dumps(notified))
                            print(f"You've saved {count} things about {subject}. {label}")
                            break
                except Exception:
                    pass
        except Exception:
            pass
