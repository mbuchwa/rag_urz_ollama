"""Vector retrieval utilities used by the chat endpoints."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import List, Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..ingest import embeddings
from ..models import Chunk, Document
from ..models.documents import DocumentStatus
from . import ranker

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetrievedChunk:
    """Lightweight representation of a retrieved chunk."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    text: str
    score: float
    ordinal: int
    title: str | None
    metadata: dict | None


def _build_query_statement(vector: Sequence[float], namespace_id: uuid.UUID, limit: int) -> Select:
    """Return the base statement for a similarity search."""

    distance = Chunk.vector.cosine_distance(vector)
    stmt = (
        select(
            Chunk.id.label("chunk_id"),
            Chunk.document_id.label("document_id"),
            Chunk.text.label("text"),
            Chunk.metadata.label("metadata"),
            Chunk.ordinal.label("ordinal"),
            Document.title.label("title"),
            distance.label("distance"),
        )
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.namespace_id == namespace_id,
            Chunk.vector.isnot(None),
            Document.status == DocumentStatus.INGESTED.value,
            Document.deleted_at.is_(None),
        )
        .order_by(distance)
        .limit(limit)
    )
    return stmt


def retrieve(
    query: str,
    namespace_id: uuid.UUID,
    *,
    session: Session,
    top_k: int | None = None,
) -> List[RetrievedChunk]:
    """Embed the query, run ANN search, and optionally rerank results."""

    search_text = query.strip()
    if not search_text:
        return []

    vectors = embeddings.embed([search_text])
    if not vectors:
        logger.debug("Embedding model returned no vector for query")
        return []

    target_top_k = max(top_k or settings.RETRIEVAL_TOP_K, 1)
    candidate_multiplier = (
        settings.RERANKER_CANDIDATE_MULTIPLIER if settings.RETRIEVAL_USE_RERANKER else 1
    )
    candidate_limit = max(target_top_k * candidate_multiplier, target_top_k)

    stmt = _build_query_statement(vectors[0], namespace_id, candidate_limit)
    rows = session.execute(stmt).all()

    results: List[RetrievedChunk] = [
        RetrievedChunk(
            chunk_id=row.chunk_id,
            document_id=row.document_id,
            text=row.text,
            score=float(row.distance or 0.0),
            ordinal=int(row.ordinal or 0),
            title=row.title,
            metadata=row.metadata if isinstance(row.metadata, dict) else None,
        )
        for row in rows
    ]

    if not results:
        return []

    if settings.RETRIEVAL_USE_RERANKER:
        try:
            results = ranker.rerank(search_text, results)
        except Exception:  # pragma: no cover - safety net
            logger.exception("Reranker failed; falling back to ANN ordering")

    return results[:target_top_k]
