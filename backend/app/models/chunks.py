"""Vector chunk metadata."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from pgvector.sqlalchemy import Vector

from . import Base


class Chunk(Base):
    """Individual chunk associated with a document."""

    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    namespace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_count = Column(Integer, nullable=False, default=0)
    text = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=True)
    vector = Column(Vector(1536), nullable=True)
    ordinal = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document = relationship("Document", back_populates="chunks")
    namespace = relationship("Namespace", back_populates="chunks")

    @property
    def metadata(self) -> dict | None:
        """Convenience accessor mirroring the metadata JSON column."""

        return self.metadata_

    @metadata.setter
    def metadata(self, value: dict | None) -> None:
        self.metadata_ = value
