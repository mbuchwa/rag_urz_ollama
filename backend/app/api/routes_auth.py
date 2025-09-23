"""Authentication endpoints leveraging OIDC."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/me", summary="Current user profile")
async def read_current_user() -> dict[str, str]:
    """Temporary placeholder for authenticated profile."""
    return {"message": "Authentication skeleton"}
