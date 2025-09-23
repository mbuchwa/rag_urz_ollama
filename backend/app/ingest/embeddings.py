"""Embedding utilities."""
from __future__ import annotations

import logging
import threading
from functools import lru_cache
from typing import Iterable, List, Sequence

from sentence_transformers import SentenceTransformer

from ..core.config import settings

logger = logging.getLogger(__name__)
_model_lock = threading.Lock()
_cached_model: SentenceTransformer | None = None
_cached_model_name: str | None = None


def get_model(model_name: str | None = None) -> SentenceTransformer:
    """Return a cached sentence-transformers model instance."""

    name = model_name or settings.EMBEDDING_MODEL_NAME

    global _cached_model, _cached_model_name
    with _model_lock:
        if _cached_model is None or _cached_model_name != name:
            logger.info("Loading embedding model: %s", name)
            _cached_model = SentenceTransformer(name)
            _cached_model_name = name
    return _cached_model


def embed(
    chunks: Iterable[str],
    *,
    model_name: str | None = None,
    embedding_dim: int | None = None,
) -> List[List[float]]:
    """Generate embeddings for the provided chunks."""

    texts = [chunk.strip() for chunk in chunks if chunk and chunk.strip()]
    if not texts:
        return []

    model = get_model(model_name)
    embeddings = model.encode(
        texts,
        batch_size=32,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=False,
    )

    target_dim = embedding_dim or settings.EMBEDDING_DIM
    return [_pad_vector(row.tolist(), target_dim) for row in embeddings]


@lru_cache(maxsize=1)
def embedding_dimension(model_name: str | None = None) -> int:
    """Return the dimension of the configured embedding model."""

    model = get_model(model_name)
    vector = model.encode(["dimension probe"], convert_to_numpy=True)
    return int(vector.shape[1]) if hasattr(vector, "shape") else len(vector[0])


def _pad_vector(vector: Sequence[float], target_dim: int) -> List[float]:
    values = list(vector)
    if len(values) == target_dim:
        return values
    if len(values) > target_dim:
        logger.debug("Truncating embedding vector from %s to %s dimensions", len(values), target_dim)
        return values[:target_dim]
    padded = values + [0.0] * (target_dim - len(values))
    return padded
