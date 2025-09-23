"""Conversation persistence models."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from . import Base


class Conversation(Base):
    """Stored conversation history scoped by namespace."""

    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    namespace_id = Column(UUID(as_uuid=True), ForeignKey("namespaces.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ConversationMessage(Base):
    """Individual message belonging to a conversation."""

    __tablename__ = "conversation_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
