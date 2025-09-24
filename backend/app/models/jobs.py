"""Background job metadata."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from . import Base


class Job(Base):
    """Celery job tracking for ingestion and retrieval tasks."""

    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    namespace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    error = Column(Text, nullable=True)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    namespace = relationship("Namespace", back_populates="jobs")
    crawl_results = relationship(
        "CrawlResult",
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
