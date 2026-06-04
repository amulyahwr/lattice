"""lattice.cli: lc — one-liner capture from the terminal."""
from __future__ import annotations

import sys


def lc() -> None:
    if len(sys.argv) < 2:
        print("Usage: lc <text>", file=sys.stderr)
        print("Example: lc \"decided to use Postgres for the new service\"", file=sys.stderr)
        sys.exit(1)

    text = " ".join(sys.argv[1:])

    from lattice.client import DaemonClient
    client = DaemonClient()
    try:
        atom_ids = client.ingest(text, source_id="lc")
    except (RuntimeError, OSError):
        print("Lattice daemon not running. Start with: lattice-daemon", file=sys.stderr)
        sys.exit(1)

    print(f"✓ captured ({len(atom_ids)} atoms)")
