"""Celery tasks for asynchronous processing."""
from __future__ import annotations

from .celery_app import celery_app


@celery_app.task(name="workers.debug")
def debug_task(message: str) -> str:
    """Simple Celery task used as a heartbeat."""
    return f"Debug: {message}"
