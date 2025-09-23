"""Namespace model for multitenancy."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID

from . import Base


class Namespace(Base):
    """Tenant namespace enforced across resources."""

    __tablename__ = "namespaces"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    slug = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
