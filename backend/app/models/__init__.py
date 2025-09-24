"""SQLAlchemy declarative base for the application models."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# Import models so that Alembic discovers the tables via Base.metadata.
# The imports are intentionally placed at the end of the module to avoid
# circular import issues when the individual model modules import ``Base``.
from .chunks import Chunk  # noqa: F401  (re-export for convenience)
from .conversations import Conversation  # noqa: F401
from .crawl_results import CrawlResult  # noqa: F401
from .documents import Document  # noqa: F401
from .jobs import Job  # noqa: F401
from .messages import Message  # noqa: F401
from .namespace_members import NamespaceMember  # noqa: F401
from .namespaces import Namespace  # noqa: F401
from .users import User  # noqa: F401


__all__ = [
    "Base",
    "Chunk",
    "Conversation",
    "Document",
    "CrawlResult",
    "Job",
    "Message",
    "Namespace",
    "NamespaceMember",
    "User",
]
