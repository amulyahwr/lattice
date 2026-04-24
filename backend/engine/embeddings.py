"""Embedding generation using sentence-transformers."""

from sentence_transformers import SentenceTransformer

from backend.config import settings

_model = None


def get_model() -> SentenceTransformer:
    """Lazy-load the embedding model."""
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed_text(text: str) -> list[float]:
    """Generate embedding for a single text."""
    model = get_model()
    return model.encode(text).tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts."""
    model = get_model()
    return model.encode(texts).tolist()
