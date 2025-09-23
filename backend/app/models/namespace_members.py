"""Association model between users and namespaces."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from . import Base


class NamespaceMember(Base):
    """Bridge table linking users to namespaces with a specific role."""

    __tablename__ = "namespace_members"
    __table_args__ = (
        UniqueConstraint("namespace_id", "user_id", name="uq_namespace_members_user_namespace"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    namespace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String, nullable=False, default="member")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    namespace = relationship("Namespace", back_populates="members")
    user = relationship("User", back_populates="namespaces")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"NamespaceMember(id={self.id!s}, namespace_id={self.namespace_id!s}, "
            f"user_id={self.user_id!s}, role={self.role!r})"
        )
