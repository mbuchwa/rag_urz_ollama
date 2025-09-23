"""Document metadata stored in the relational database."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID

from . import Base


class Document(Base):
    """An ingested document belonging to a namespace."""

    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    namespace_id = Column(UUID(as_uuid=True), ForeignKey("namespaces.id", ondelete="CASCADE"), nullable=False)
    uri = Column(String, nullable=False)
    content_type = Column(String, nullable=False, default="text/plain")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
