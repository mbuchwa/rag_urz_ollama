"""Shared SlowAPI rate limiter configuration."""
from __future__ import annotations

import logging
from typing import Callable

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


def _user_or_ip_key(request: Request) -> str:
    """Return the rate limit bucket key for the current request."""

    # Prefer the authenticated user identifier when available so that
    # concurrent clients behind the same proxy do not throttle each other.
    session_user = None
    try:
        session_user = request.session.get("user_id")  # type: ignore[union-attr]
    except Exception:  # pragma: no cover - defensive for unexpected middleware order
        session_user = None

    if session_user:
        return str(session_user)

    state_user = getattr(request.state, "user_id", None)
    if state_user:
        return str(state_user)

    return get_remote_address(request)


limiter = Limiter(key_func=_user_or_ip_key)


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return a JSON response when a rate limit is exceeded."""

    logger.warning(
        "Rate limit exceeded for path=%s key=%s", request.url.path, exc.detail
    )
    return JSONResponse(
        {"detail": "Rate limit exceeded"},
        status_code=exc.status_code,
        headers={"Retry-After": str(exc.retry_after)} if exc.retry_after else None,
    )


RateLimitHandler = Callable[[Request, RateLimitExceeded], JSONResponse]

