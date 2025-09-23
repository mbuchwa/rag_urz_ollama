"""Administrative API endpoints."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", summary="Readiness probe")
async def admin_health() -> dict[str, str]:
    """Administrative health endpoint."""
    return {"status": "ok"}
