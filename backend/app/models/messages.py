"""Conversation message persistence model."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from . import Base


class Message(Base):
    """Individual message belonging to a conversation."""

    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation = relationship("Conversation", back_populates="messages")
    user = relationship("User", back_populates="messages")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Message(id={self.id!s}, conversation_id={self.conversation_id!s}, role={self.role!r})"

    @property
    def metadata(self) -> dict | None:
        """Expose message metadata while avoiding attribute name clashes."""

        return self.metadata_

    @metadata.setter
    def metadata(self, value: dict | None) -> None:
        self.metadata_ = value
