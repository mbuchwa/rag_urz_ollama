"""User model definition."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from . import Base


class User(Base):
    """Application user persisted via OIDC identity."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    email = Column(String, nullable=False, unique=True, index=True)
    display_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    namespaces = relationship(
        "NamespaceMember",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    conversations = relationship("Conversation", back_populates="user")
    messages = relationship("Message", back_populates="user")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"User(id={self.id!s}, email={self.email!r})"
