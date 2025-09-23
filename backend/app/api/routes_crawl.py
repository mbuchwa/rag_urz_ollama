"""Crawl management endpoints."""
from fastapi import APIRouter

router = APIRouter()


@router.post("/trigger", summary="Trigger crawl job")
async def trigger_crawl() -> dict[str, str]:
    """Placeholder for triggering crawl workers."""
    return {"message": "Crawl triggered"}
