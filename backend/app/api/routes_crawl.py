"""Crawl management endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.db import get_session
from ..core.rate_limiter import limiter
from ..models import CrawlResult, Job, NamespaceMember
from ..workers.tasks import crawl_site

router = APIRouter()


class CrawlStartRequest(BaseModel):
    url: HttpUrl
    namespace_id: uuid.UUID
    depth: int = Field(default=2, ge=0, le=3)


class CrawlStartResponse(BaseModel):
    job_id: uuid.UUID


class CrawlJobSummary(BaseModel):
    id: uuid.UUID
    namespace_id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime | None
    url: str
    depth: int
    total_count: int
    harvested_count: int
    failed_count: int
    blocked_count: int
    skipped_count: int
    error: str | None


class CrawlJobListResponse(BaseModel):
    jobs: list[CrawlJobSummary]


class CrawlResultRecord(BaseModel):
    id: uuid.UUID
    url: str
    depth: int
    status: str
    content_type: str | None
    document_id: uuid.UUID | None
    error: str | None
    created_at: datetime


class CrawlJobDetailResponse(BaseModel):
    job: CrawlJobSummary
    results: list[CrawlResultRecord]


@router.post("/start", response_model=CrawlStartResponse, summary="Start a crawl job")
@limiter.limit(settings.RATE_LIMIT_CRAWL)
async def start_crawl(
    payload: CrawlStartRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> CrawlStartResponse:
    """Create a crawl job and enqueue the asynchronous worker."""

    user_id = _require_user_id(request)
    _assert_namespace_membership(session, payload.namespace_id, user_id)

    job = Job(
        namespace_id=payload.namespace_id,
        task_type="crawl",
        status="queued",
        payload={"url": str(payload.url), "depth": payload.depth},
    )
    session.add(job)
    session.flush()

    crawl_site.delay(str(job.id))

    return CrawlStartResponse(job_id=job.id)


@router.get("/jobs", response_model=CrawlJobListResponse, summary="List crawl jobs")
async def list_crawl_jobs(
    request: Request,
    session: Session = Depends(get_session),
    namespace_id: uuid.UUID | None = Query(None),
) -> CrawlJobListResponse:
    """Return all crawl jobs for the authenticated user."""

    user_id = _require_user_id(request)
    allowed = _user_namespace_ids(session, user_id)

    if namespace_id is not None:
        if namespace_id not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Namespace access denied")
        namespace_ids = {namespace_id}
    else:
        namespace_ids = allowed

    if not namespace_ids:
        return CrawlJobListResponse(jobs=[])

    stmt = _build_job_query().where(Job.namespace_id.in_(list(namespace_ids)))
    rows = session.execute(stmt).all()
    jobs = [_build_job_summary(row) for row in rows]
    return CrawlJobListResponse(jobs=jobs)


@router.get("/{job_id}", response_model=CrawlJobDetailResponse, summary="Get crawl job details")
async def get_crawl_job(
    job_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
) -> CrawlJobDetailResponse:
    """Return job metadata and harvested URLs for a crawl job."""

    user_id = _require_user_id(request)

    job = session.get(Job, job_id)
    if job is None or job.task_type != "crawl":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    _assert_namespace_membership(session, job.namespace_id, user_id)

    row = session.execute(_build_job_query().where(Job.id == job_id)).one()
    summary = _build_job_summary(row)

    results_stmt: Select[Any] = (
        select(CrawlResult)
        .where(CrawlResult.job_id == job_id)
        .order_by(CrawlResult.created_at.asc())
    )
    results = session.execute(results_stmt).scalars().all()

    return CrawlJobDetailResponse(job=summary, results=[_to_result_record(item) for item in results])


def _build_job_query() -> Select[Any]:
    harvested = func.coalesce(func.sum(case((CrawlResult.status == "harvested", 1), else_=0)), 0).label("harvested")
    failed = func.coalesce(func.sum(case((CrawlResult.status == "failed", 1), else_=0)), 0).label("failed")
    blocked = func.coalesce(func.sum(case((CrawlResult.status == "blocked", 1), else_=0)), 0).label("blocked")
    skipped = func.coalesce(func.sum(case((CrawlResult.status == "skipped", 1), else_=0)), 0).label("skipped")
    total = func.count(CrawlResult.id).label("total")

    return (
        select(Job, total, harvested, failed, blocked, skipped)
        .outerjoin(CrawlResult, CrawlResult.job_id == Job.id)
        .where(Job.task_type == "crawl")
        .group_by(Job.id)
        .order_by(Job.created_at.desc())
    )


def _build_job_summary(row: Any) -> CrawlJobSummary:
    job: Job = row.Job
    payload = job.payload or {}
    url = str(payload.get("url") or "")
    depth_value = payload.get("depth", 2)
    try:
        depth = int(depth_value)
    except (TypeError, ValueError):
        depth = 2

    return CrawlJobSummary(
        id=job.id,
        namespace_id=job.namespace_id,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        url=url,
        depth=depth,
        total_count=int(row.total or 0),
        harvested_count=int(row.harvested or 0),
        failed_count=int(row.failed or 0),
        blocked_count=int(row.blocked or 0),
        skipped_count=int(row.skipped or 0),
        error=job.error,
    )


def _to_result_record(result: CrawlResult) -> CrawlResultRecord:
    return CrawlResultRecord(
        id=result.id,
        url=result.url,
        depth=result.depth,
        status=result.status,
        content_type=result.content_type,
        document_id=result.document_id,
        error=result.error,
        created_at=result.created_at,
    )


def _require_user_id(request: Request) -> uuid.UUID:
    raw_user_id = getattr(request.state, "user_id", None)
    if not raw_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return uuid.UUID(str(raw_user_id))
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc


def _assert_namespace_membership(session: Session, namespace_id: uuid.UUID, user_id: uuid.UUID) -> None:
    stmt: Select[Any] = select(NamespaceMember.id).where(
        NamespaceMember.namespace_id == namespace_id,
        NamespaceMember.user_id == user_id,
    )
    exists = session.execute(stmt).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Namespace access denied")


def _user_namespace_ids(session: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    stmt: Select[Any] = select(NamespaceMember.namespace_id).where(NamespaceMember.user_id == user_id)
    return {row[0] for row in session.execute(stmt).all()}
