"""Document management endpoints."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/", summary="List documents")
async def list_documents() -> dict[str, str]:
    """Placeholder for listing indexed documents."""
    return {"message": "Documents endpoint stub"}
