"""User model definition."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID

from . import Base


class User(Base):
    """Application user persisted via OIDC identity."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    email = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
