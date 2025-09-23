"""Chat endpoints for the RAG assistant."""
from fastapi import APIRouter

router = APIRouter()


@router.post("/", summary="Chat completion")
async def chat_completion() -> dict[str, str]:
    """Placeholder endpoint for chat responses."""
    return {"message": "Chat endpoint stub"}
