"""Document metadata stored in the relational database."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from . import Base


class Document(Base):
    """An ingested document belonging to a namespace."""

    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    namespace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uri = Column(String, nullable=False)
    title = Column(String, nullable=True)
    content_type = Column(String, nullable=False, default="text/plain")
    metadata_ = Column("metadata", JSONB, nullable=True)
    text_preview = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    namespace = relationship("Namespace", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")

    @property
    def metadata(self) -> dict | None:
        """Return document metadata stored in the JSONB column."""

        return self.metadata_

    @metadata.setter
    def metadata(self, value: dict | None) -> None:
        self.metadata_ = value
