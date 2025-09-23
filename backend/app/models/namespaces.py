"""Namespace model for multitenancy."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from . import Base


class Namespace(Base):
    """Tenant namespace enforced across resources."""

    __tablename__ = "namespaces"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    slug = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    members = relationship(
        "NamespaceMember",
        back_populates="namespace",
        cascade="all, delete-orphan",
    )
    documents = relationship("Document", back_populates="namespace", cascade="all, delete-orphan")
    chunks = relationship("Chunk", back_populates="namespace", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="namespace", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="namespace", cascade="all, delete-orphan")
