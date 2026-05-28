from __future__ import annotations

import os
from typing import Any

import numpy as np

from lattice.models import Atom

# ── optional fastembed ────────────────────────────────────────────────────────

try:
    from fastembed import TextEmbedding as _TextEmbedding
    _EMBED_AVAILABLE = True
except ImportError:
    _EMBED_AVAILABLE = False

_embed_model: Any = None


def is_available() -> bool:
    return _EMBED_AVAILABLE


def _get_model() -> Any:
    global _embed_model
    if _embed_model is None:
        model_name = os.environ.get("LATTICE_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
        _embed_model = _TextEmbedding(model_name)
    return _embed_model


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0


def embed_texts(texts: list[str]) -> list[np.ndarray]:
    """Embed a list of texts. Returns one ndarray per text."""
    model = _get_model()
    return [np.array(v) for v in model.embed(texts)]


def _rerank(query: str, atoms: list[Atom]) -> list[Atom]:
    if not _EMBED_AVAILABLE or not atoms:
        return atoms
    texts = [query] + [f"{a.subject} {a.content[:300]}" for a in atoms]
    vecs = embed_texts(texts)
    q_vec = vecs[0]
    scored = sorted(
        zip(atoms, vecs[1:]),
        key=lambda x: _cosine(q_vec, x[1]),
        reverse=True,
    )
    return [a for a, _ in scored]


def rerank_seeds(query: str, seeds: list[Atom]) -> list[Atom]:
    return _rerank(query, seeds)


def rerank_atoms(query: str, atoms: list[Atom]) -> list[Atom]:
    """Re-rank expanded atom pack by cosine similarity to query."""
    return _rerank(query, atoms)


def rerank_atom_dicts(query: str, atoms: list[dict]) -> list[dict]:
    """Re-rank atom dicts (subject+content) by cosine similarity to query.

    Falls back to original order if fastembed not available or atoms empty.
    """
    if not _EMBED_AVAILABLE or not atoms:
        return atoms
    texts = [query] + [f"{a.get('subject', '')} {str(a.get('content', ''))[:300]}" for a in atoms]
    vecs = embed_texts(texts)
    q_vec = vecs[0]
    scored = sorted(
        zip(atoms, vecs[1:]),
        key=lambda x: _cosine(q_vec, x[1]),
        reverse=True,
    )
    return [a for a, _ in scored]
