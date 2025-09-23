"""OIDC client configuration using Authlib."""
from __future__ import annotations

from functools import lru_cache

from authlib.integrations.starlette_client import OAuth

from ..core.config import settings


@lru_cache(maxsize=1)
def get_oidc_client() -> OAuth:
    """Return a configured Authlib OAuth client for the OIDC provider."""

    oauth = OAuth()
    issuer = settings.OIDC_ISSUER.rstrip("/")
    oauth.register(
        name="oidc",
        server_metadata_url=f"{issuer}/.well-known/openid-configuration",
        client_id=settings.OIDC_CLIENT_ID,
        client_secret=settings.OIDC_CLIENT_SECRET,
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth
