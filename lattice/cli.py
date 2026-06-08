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

        _MILESTONES = {1: "First day. Good start.", 7: "A week in. Lattice is starting to know you.", 30: "30 days. You've built something here."}
        msg = (f"Two weeks of asking and remembering. You have {count} things stored — this is becoming real." if streak == 14 else _MILESTONES.get(streak))
        if msg:
            print(msg)
        return

    arg = " ".join(sys.argv[1:])

    # If the argument is a path to an existing file, extract its text
    from pathlib import Path as _Path
    _arg_path = _Path(arg)
    source_id = "lc"
    if _arg_path.exists() and _arg_path.is_file():
        from lattice.util import extract_file_text
        try:
            text, source_id = extract_file_text(_arg_path)
        except ImportError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
    else:
        text = arg

    from lattice.client import DaemonClient
    try:
        result = DaemonClient().ingest_full(text, source_id=source_id)
    except (RuntimeError, OSError):
        print("Lattice daemon not running. Start with: lattice-daemon", file=sys.stderr)
        sys.exit(1)

    added   = result.get("atoms_new", 0)
    updated = result.get("atoms_updated", 0)
    skipped = result.get("duplicates_skipped", 0)

    s = lambda n: "s" if n != 1 else ""
    if added == 0 and updated == 0:
        print("Already knew all of this — nothing new.")
    elif added and updated:
        print(f"Saved. {added} new idea{s(added)} picked up, {updated} refreshed with newer info.")
    elif added:
        print(f"Saved. {added} new idea{s(added)} added to your memory.")
    else:
        print(f"Saved. {updated} thing{s(updated)} refreshed with newer info.")

    # Topic depth check — notify once per subject when threshold crossed
    atom_ids = result.get("atom_ids", [])
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
