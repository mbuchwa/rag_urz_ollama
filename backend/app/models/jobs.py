"""Background job metadata."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID

from . import Base


class Job(Base):
    """Celery job tracking for ingestion and retrieval tasks."""

    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    namespace_id = Column(UUID(as_uuid=True), ForeignKey("namespaces.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
