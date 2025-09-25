"""Database utilities for SQLAlchemy and Alembic."""
from __future__ import annotations

from typing import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings


def _create_engine() -> Engine:
    """Create the SQLAlchemy engine using application settings."""

    return create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)


ENGINE: Engine = _create_engine()
SessionLocal = sessionmaker[
    Session
](bind=ENGINE, autoflush=False, autocommit=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:  # pragma: no cover - defensive rollback
        session.rollback()
        raise
    finally:
        session.close()
