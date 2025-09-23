"""Vector chunk metadata."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID

from . import Base


class Chunk(Base):
    """Individual chunk associated with a document."""

    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    namespace_id = Column(UUID(as_uuid=True), ForeignKey("namespaces.id", ondelete="CASCADE"), nullable=False)
    token_count = Column(Integer, nullable=False, default=0)
    text = Column(String, nullable=False)
    metadata_json = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
