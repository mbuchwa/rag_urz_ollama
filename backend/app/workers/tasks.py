"""Celery tasks for asynchronous processing."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete

from ..core.config import settings
from ..core.db import SessionLocal
from ..core.s3 import get_minio_client
from ..ingest import chunking, embeddings, parsers
from ..models import Chunk, Document, Job
from ..models.documents import DocumentStatus
from .celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="workers.debug")
def debug_task(message: str) -> str:
    """Simple Celery task used as a heartbeat."""

    return f"Debug: {message}"


@celery_app.task(name="workers.ingest_document")
def ingest_document(document_id: str, job_id: str | None = None) -> str:
    """Ingest a document by parsing, chunking, and embedding its contents."""

    session = SessionLocal()
    job: Job | None = None

    try:
        document_uuid = uuid.UUID(document_id)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        logger.error("Invalid document id provided to ingest task: %s", exc)
        session.close()
        return "invalid"

    try:
        document = session.get(Document, document_uuid)
        if document is None:
            logger.error("Document %s not found for ingestion", document_uuid)
            return "missing"
        if document.deleted_at:
            logger.info("Skipping ingestion for deleted document %s", document_uuid)
            return "deleted"

        if job_id:
            try:
                job_uuid = uuid.UUID(job_id)
                job = session.get(Job, job_uuid)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                logger.warning("Ignoring invalid job id passed to ingest_document: %s", job_id)
        if job:
            job.status = "running"
            job.error = None
            job.updated_at = datetime.now(timezone.utc)

        document.status = DocumentStatus.PROCESSING.value
        document.error = None
        session.flush()

        content = _download_document(document.uri)
        metadata = document.metadata or {}
        parsed = parsers.parse_bytes(
            content,
            content_type=document.content_type,
            filename=metadata.get("original_filename"),
        )
        if not parsed.text:
            raise ValueError("Parsed document produced no text")

        chunks = chunking.chunk_text(parsed.text)
        if not chunks:
            raise ValueError("No chunks generated from document text")

        vectors = embeddings.embed([chunk.text for chunk in chunks])
        if len(vectors) != len(chunks):
            raise RuntimeError("Mismatch between chunk count and embedding count")

        session.execute(delete(Chunk).where(Chunk.document_id == document.id))

        source_url = metadata.get("source_url") if isinstance(metadata, dict) else None
        for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
            chunk_meta: dict[str, Any] = {}
            if source_url:
                chunk_meta["source_url"] = source_url
            if chunk.headings:
                chunk_meta["headings"] = chunk.headings
            session.add(
                Chunk(
                    document_id=document.id,
                    namespace_id=document.namespace_id,
                    text=chunk.text,
                    token_count=_estimate_tokens(chunk.text),
                    metadata=chunk_meta or None,
                    vector=vector,
                    ordinal=idx,
                )
            )

        document.status = DocumentStatus.INGESTED.value
        document.text_preview = chunks[0].text[:500]
        metadata = document.metadata or {}
        metadata["chunk_count"] = len(chunks)
        document.metadata = metadata
        document.updated_at = datetime.now(timezone.utc)

        if job:
            job.status = "succeeded"
            job.error = None
            job.updated_at = datetime.now(timezone.utc)

        session.commit()
        logger.info("Ingested document %s with %s chunks", document.id, len(chunks))
        return "ingested"
    except Exception as exc:  # pragma: no cover - defensive logging
        session.rollback()
        logger.exception("Failed to ingest document %s: %s", document_id, exc)
        failure_message = str(exc)

        try:
            document = session.get(Document, document_uuid)
            if document:
                document.status = DocumentStatus.FAILED.value
                document.error = failure_message[:1000]
                document.updated_at = datetime.now(timezone.utc)
                session.flush()
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to mark document %s as failed", document_id)

        if job:
            try:
                job.status = "failed"
                job.error = failure_message[:1000]
                job.updated_at = datetime.now(timezone.utc)
                session.flush()
            except Exception:  # pragma: no cover - defensive
                logger.exception("Failed to update job %s failure state", job_id)

        session.commit()
        return "failed"
    finally:
        session.close()


def _download_document(object_key: str) -> bytes:
    client = get_minio_client()
    response = client.get_object(settings.MINIO_BUCKET, object_key)
    try:
        data = response.read()
    finally:
        response.close()
        response.release_conn()
    return data


def _estimate_tokens(text: str) -> int:
    return max(len(text.split()), 1)
