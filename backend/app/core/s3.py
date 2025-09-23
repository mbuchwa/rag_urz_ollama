"""MinIO client helpers for storing documents."""
from __future__ import annotations

from minio import Minio

from .config import settings


def get_minio_client() -> Minio:
    """Return a configured MinIO client."""
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=False,
    )
