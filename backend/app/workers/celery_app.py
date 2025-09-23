"""Celery application configuration."""
from __future__ import annotations

from celery import Celery

from ..core.config import settings

celery_app = Celery(
    "urz_rag",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["backend.app.workers.tasks"],
)

celery_app.conf.update(task_default_queue="default")
