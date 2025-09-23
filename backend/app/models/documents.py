"""Document metadata stored in the relational database."""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from . import Base


class DocumentStatus(str, enum.Enum):
    """Lifecycle states for an ingested document."""

    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    INGESTED = "ingested"
    FAILED = "failed"
    DELETED = "deleted"


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
    status = Column(
        String,
        nullable=False,
        default=DocumentStatus.UPLOADING.value,
        server_default=DocumentStatus.UPLOADING.value,
    )
    error = Column(Text, nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
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

    @property
    def is_deleted(self) -> bool:
        """Return whether the document has been soft deleted."""

        return self.deleted_at is not None or self.status == DocumentStatus.DELETED.value

    def mark_deleted(self) -> None:
        """Soft delete the document by updating status and timestamp."""

        self.status = DocumentStatus.DELETED.value
        self.deleted_at = datetime.now(timezone.utc)
