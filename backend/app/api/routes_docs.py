"""Document management endpoints."""
from __future__ import annotations

import logging
import mimetypes
import re
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, urlunparse
from typing import Any, Iterable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from ..core.antivirus import ScanError, get_scanner
from ..core.config import settings
from ..core.db import get_session
from ..core.rate_limiter import limiter
from ..core.s3 import get_minio_client
from ..models import Chunk, Document, Job, NamespaceMember
from ..models.documents import DocumentStatus
from ..workers.tasks import ingest_document

logger = logging.getLogger(__name__)
router = APIRouter()

FILENAME_CLEANER = re.compile(r"[^A-Za-z0-9._-]+")
ALLOWED_UPLOAD_TYPES = {value.lower() for value in settings.UPLOAD_ALLOWED_MIME_TYPES}


class UploadInitRequest(BaseModel):
    namespace_id: uuid.UUID
    filename: str = Field(..., min_length=1, max_length=512)
    content_type: Optional[str] = Field(default=None, max_length=255)


class UploadInitResponse(BaseModel):
    document_id: uuid.UUID
    upload_url: str


class UploadCompleteRequest(BaseModel):
    document_id: uuid.UUID
    namespace_id: uuid.UUID
    title: Optional[str] = Field(default=None, max_length=255)
    source_url: Optional[str] = Field(default=None, max_length=2048)
    metadata: Optional[dict[str, Any]] = None

    def model_dump(self, *args, **kwargs):  # type: ignore[override]
        if "mode" not in kwargs:
            kwargs["mode"] = "json"
        return super().model_dump(*args, **kwargs)


class DocumentResponse(BaseModel):
    id: uuid.UUID
    namespace_id: uuid.UUID
    uri: str
    title: Optional[str]
    status: str
    content_type: str
    created_at: datetime
    updated_at: Optional[datetime]
    text_preview: Optional[str]
    metadata: Optional[dict[str, Any]]
    error: Optional[str]
    chunk_count: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]


def _normalize_filename(filename: str) -> str:
    base = filename.strip()
    if not base:
        return "document"
    cleaned = FILENAME_CLEANER.sub("_", base)
    return cleaned.strip("._") or "document"


def _infer_content_type(filename: str, provided: str | None) -> str:
    if provided and provided.strip():
        return provided.split(";", 1)[0].strip()
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _build_object_key(namespace_id: uuid.UUID, document_id: uuid.UUID, filename: str) -> str:
    return f"uploads/{namespace_id}/{document_id}/{filename}"


def _externalize_presigned_url(url: str) -> str:
    """Rewrite a presigned URL to use the configured public MinIO endpoint."""

    public_endpoint = settings.MINIO_PUBLIC_ENDPOINT
    if not public_endpoint:
        return url

    normalized_endpoint = (
        public_endpoint
        if "://" in public_endpoint
        else f"https://{public_endpoint}"
    )
    parsed_public = urlparse(normalized_endpoint)
    netloc = parsed_public.netloc or parsed_public.path
    if not netloc:
        return url

    parsed_url = urlparse(url)
    scheme = parsed_public.scheme or parsed_url.scheme or "https"
    base_path = parsed_public.path.rstrip("/")
    path = f"{base_path}{parsed_url.path}" if base_path else parsed_url.path

    return urlunparse(
        parsed_url._replace(
            scheme=scheme,
            netloc=netloc,
            path=path,
        )
    )


def _require_user_id(request: Request) -> uuid.UUID:
    raw_user_id = getattr(request.state, "user_id", None)
    if not raw_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return uuid.UUID(str(raw_user_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from None


def _assert_namespace_membership(session: Session, namespace_id: uuid.UUID, user_id: uuid.UUID) -> None:
    stmt: Select[Any] = select(NamespaceMember.id).where(
        NamespaceMember.namespace_id == namespace_id,
        NamespaceMember.user_id == user_id,
    )
    exists = session.execute(stmt).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Namespace access denied")


async def _ensure_bucket() -> None:
    client = get_minio_client()
    exists = await run_in_threadpool(client.bucket_exists, settings.MINIO_BUCKET)
    if not exists:
        await run_in_threadpool(client.make_bucket, settings.MINIO_BUCKET)


@router.post(
    "/upload-init",
    response_model=UploadInitResponse,
    summary="Begin a document upload",
)
@limiter.limit(settings.RATE_LIMIT_INGESTION)
async def upload_init(
    payload: UploadInitRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> UploadInitResponse:
    """Create a document record and return a pre-signed upload URL."""

    user_id = _require_user_id(request)
    _assert_namespace_membership(session, payload.namespace_id, user_id)

    filename = _normalize_filename(payload.filename)
    content_type = _validate_content_type(
        _infer_content_type(filename, payload.content_type)
    )

    document = Document(
        namespace_id=payload.namespace_id,
        uri="",  # placeholder until we derive object key
        title=None,
        content_type=content_type,
        metadata_dict={"original_filename": payload.filename},
        status=DocumentStatus.UPLOADING.value,
    )
    session.add(document)
    session.flush()

    object_key = _build_object_key(payload.namespace_id, document.id, filename)
    document.uri = object_key
    session.flush()

    await _ensure_bucket()

    client = get_minio_client()
    upload_url = await run_in_threadpool(
        client.presigned_put_object,
        settings.MINIO_BUCKET,
        object_key,
        expires=timedelta(minutes=15),
    )
    upload_url = _externalize_presigned_url(upload_url)

    logger.info("Initialized upload for document %s in namespace %s", document.id, payload.namespace_id)
    return UploadInitResponse(document_id=document.id, upload_url=upload_url)


@router.post(
    "/complete",
    response_model=DocumentResponse,
    summary="Finalize an uploaded document",
)
@limiter.limit(settings.RATE_LIMIT_INGESTION)
async def upload_complete(
    payload: UploadCompleteRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> DocumentResponse:
    """Mark a document upload as complete and enqueue ingestion."""

    user_id = _require_user_id(request)
    _assert_namespace_membership(session, payload.namespace_id, user_id)

    document = session.get(Document, payload.document_id)
    if document is None or document.namespace_id != payload.namespace_id or document.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    document.title = (
        payload.title
        or document.title
        or (document.metadata_dict or {}).get("original_filename")
    )
    size, stored_content_type = await _stat_uploaded_object(document)
    stored_content_type = _validate_content_type(stored_content_type)
    _ensure_within_size_limit(size)

    scanner = get_scanner()
    try:
        await run_in_threadpool(
            scanner.scan,
            bucket=settings.MINIO_BUCKET,
            object_key=document.uri,
            size=size,
            content_type=stored_content_type,
        )
    except ScanError as exc:
        logger.warning(
            "Upload flagged by antivirus scanner document=%s error=%s",
            document.id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file failed virus scan",
        ) from exc

    document.status = DocumentStatus.UPLOADED.value
    document.error = None
    metadata = document.metadata_dict or {}
    if payload.source_url:
        metadata["source_url"] = payload.source_url
    if payload.metadata:
        metadata.update(payload.metadata)
    metadata["size_bytes"] = size
    document.metadata_dict = metadata
    document.content_type = stored_content_type
    document.updated_at = datetime.now(timezone.utc)

    job = Job(
        namespace_id=document.namespace_id,
        task_type="document_ingest",
        status="queued",
        payload={"document_id": str(document.id)},
    )
    session.add(job)
    session.flush()

    ingest_document.delay(str(document.id), str(job.id))

    return _to_document_response(document, chunk_count=_count_chunks(session, document.id))


@router.get("/", response_model=DocumentListResponse, summary="List documents")
async def list_documents(
    request: Request,
    namespace_id: uuid.UUID = Query(...),
    status_filter: Iterable[str] | None = Query(None, alias="status"),
    session: Session = Depends(get_session),
) -> DocumentListResponse:
    """Return all documents for a namespace filtered by status."""

    user_id = _require_user_id(request)
    _assert_namespace_membership(session, namespace_id, user_id)

    statuses: set[str] | None = None
    if status_filter:
        statuses = {value.lower() for value in status_filter if value}

    stmt = (
        select(Document, func.count(Chunk.id))
        .join(Chunk, Chunk.document_id == Document.id, isouter=True)
        .where(Document.namespace_id == namespace_id)
        .where(Document.deleted_at.is_(None))
        .group_by(Document.id)
        .order_by(Document.created_at.desc())
    )
    if statuses:
        stmt = stmt.where(Document.status.in_(list(statuses)))

    results = session.execute(stmt).all()
    documents = [_to_document_response(doc, chunk_count=count) for doc, count in results]
    return DocumentListResponse(documents=documents)


@router.delete("/{document_id}", summary="Soft delete a document")
async def delete_document(
    document_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    """Soft delete a document and remove associated chunks."""

    user_id = _require_user_id(request)

    document = session.get(Document, document_id)
    if document is None or document.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    _assert_namespace_membership(session, document.namespace_id, user_id)

    document.mark_deleted()
    document.error = None
    document.text_preview = None

    session.execute(delete(Chunk).where(Chunk.document_id == document.id))

    return {"detail": "Document deleted"}


def _count_chunks(session: Session, document_id: uuid.UUID) -> int:
    stmt = select(func.count(Chunk.id)).where(Chunk.document_id == document_id)
    return int(session.execute(stmt).scalar_one() or 0)


def _to_document_response(document: Document, chunk_count: int) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        namespace_id=document.namespace_id,
        uri=document.uri,
        title=document.title,
        status=document.status,
        content_type=document.content_type,
        created_at=document.created_at,
        updated_at=document.updated_at,
        text_preview=document.text_preview,
        metadata=document.metadata_dict,
        error=document.error,
        chunk_count=chunk_count,
    )


def _validate_content_type(content_type: str) -> str:
    normalized = (content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    if normalized not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type",
        )
    return normalized


def _ensure_within_size_limit(size: int) -> None:
    if size <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded object is empty",
        )
    if size > settings.UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Uploaded object exceeds size limit",
        )


async def _stat_uploaded_object(document: Document) -> tuple[int, str]:
    client = get_minio_client()
    try:
        stat = await run_in_threadpool(
            client.stat_object,
            settings.MINIO_BUCKET,
            document.uri,
        )
    except Exception as exc:  # pragma: no cover - network errors
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded object not found",
        ) from exc
    size = int(getattr(stat, "size", 0) or 0)
    content_type = getattr(stat, "content_type", document.content_type or "")
    return size, content_type
