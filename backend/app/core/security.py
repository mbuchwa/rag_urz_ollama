"""OIDC authentication utilities leveraging Authlib."""
from __future__ import annotations

from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.requests import Request

from .config import settings

oauth = OAuth()
oauth.register(
    name="oidc",
    server_metadata_url=f"{settings.OIDC_ISSUER}/.well-known/openid-configuration",
    client_id=settings.OIDC_CLIENT_ID,
    client_secret=settings.OIDC_CLIENT_SECRET,
    client_kwargs={"scope": "openid profile email"},
)

bearer_scheme = HTTPBearer(auto_error=False)


def require_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> str:
    """Ensure that a bearer token is present for protected endpoints."""
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return credentials.credentials


async def get_current_user(request: Request) -> dict[str, str]:
    """Placeholder for decoding and validating the user identity."""
    token = await oauth.oidc.authorize_access_token(request)  # type: ignore[attr-defined]
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return {"sub": token.get("sub", "unknown")}
