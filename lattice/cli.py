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
        from lattice.config import Config
        from lattice.db import LatticeDB
        db = LatticeDB(Config.from_env().lattice_dir)
        count = len([a for a in db.all() if not a.is_superseded])
        print(f"{count} memories stored")
        return

    text = " ".join(sys.argv[1:])

    from lattice.client import DaemonClient
    try:
        atom_ids = DaemonClient().ingest(text, source_id="lc")
    except (RuntimeError, OSError):
        print("Lattice daemon not running. Start with: lattice-daemon", file=sys.stderr)
        sys.exit(1)

    print(f"Saved. {len(atom_ids)} new thing{'s' if len(atom_ids) != 1 else ''} added to your memory.")
