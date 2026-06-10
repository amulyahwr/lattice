"""
One-shot script: build dense embed matrices for all question dirs in a lattice root.

Usage:
    uv run python -m lattice.eval.build_embed_index \
        --lattice-root results/p42/openaigpt4omini_longmemeval_s_cleaned_inference.lattices \
        [--workers 4]

Reads existing atoms from disk (no LLM calls). Writes embed_matrix.npy +
embed_ids.json into each question dir's graph/ folder. Safe to re-run —
skips dirs that already have a fresh embed sidecar.
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm


def _build_one(qdir: Path, cfg) -> tuple[str, int]:
    from lattice.db import LatticeDB
    db = LatticeDB(qdir)
    db.preload()
    if not db._atom_cache:
        return qdir.name, 0
    db._rebuild_embed_index()
    return qdir.name, len(db._embed_ids)


def main():
    parser = argparse.ArgumentParser(description="Build dense embed index for all lattice dirs")
    parser.add_argument("--lattice-root", required=True, help="Path to lattice root dir (contains per-question subdirs)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true", help="Rebuild even if sidecar already exists")
    args = parser.parse_args()

    root = Path(args.lattice_root)
    if not root.exists():
        print(f"ERROR: {root} does not exist", file=sys.stderr)
        sys.exit(1)

    try:
        import lattice.embed as _embed
        if not _embed.is_available():
            print("ERROR: fastembed not available. Run: uv sync --group semantic", file=sys.stderr)
            sys.exit(1)
    except ImportError:
        print("ERROR: fastembed not available. Run: uv sync --group semantic", file=sys.stderr)
        sys.exit(1)

    qdirs = [d for d in root.iterdir() if d.is_dir()]
    if not args.force:
        qdirs = [d for d in qdirs if not (d / "graph" / "embed_matrix.npy").exists()]

    print(f"Building embed index for {len(qdirs)} dirs (workers={args.workers})")
    if not qdirs:
        print("All dirs already have embed sidecars. Use --force to rebuild.")
        return

    total_atoms = 0
    errors = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_build_one, d, None): d for d in qdirs}
        with tqdm(total=len(qdirs), unit="q") as pbar:
            for fut in as_completed(futures):
                try:
                    qid, n = fut.result()
                    total_atoms += n
                    pbar.set_postfix(atoms=total_atoms)
                except Exception as e:
                    errors += 1
                    qd = futures[fut]
                    tqdm.write(f"ERROR {qd.name}: {e}")
                pbar.update(1)

    print(f"\nDone: {len(qdirs) - errors} built, {errors} errors, {total_atoms} atoms indexed")


if __name__ == "__main__":
    main()
