"""Administrative API endpoints."""
from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter()


@router.get("/health", summary="Readiness probe")
async def admin_health() -> dict[str, str]:
    """Administrative health endpoint."""
    return {"status": "ok"}


@router.get("/metrics", summary="Prometheus metrics feed")
async def admin_metrics() -> Response:
    """Expose Prometheus-formatted metrics for scraping."""

    payload = generate_latest()
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)
