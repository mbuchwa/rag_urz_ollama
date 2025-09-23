"""Custom ASGI middleware for authentication and CSRF protection."""
from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


class AuthenticatedSessionMiddleware(BaseHTTPMiddleware):
    """Ensure requests hitting API routes have a valid authenticated session."""

    def __init__(self, app: Callable, api_prefix: str = "/api") -> None:
        super().__init__(app)
        self.api_prefix = api_prefix

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path

        if path.startswith(self.api_prefix):
            session = request.session
            user_id = session.get("user_id")
            if not user_id:
                return JSONResponse({"detail": "Not authenticated"}, status_code=status.HTTP_401_UNAUTHORIZED)

            request.state.user_id = user_id

            if request.method not in SAFE_METHODS and _is_json_request(request):
                session_token = session.get("csrf_token")
                header_token = request.headers.get("X-CSRF-Token")
                if not session_token or not header_token or header_token != session_token:
                    return JSONResponse(
                        {"detail": "Invalid CSRF token"},
                        status_code=status.HTTP_403_FORBIDDEN,
                    )

        return await call_next(request)


def _is_json_request(request: Request) -> bool:
    content_type = request.headers.get("content-type")
    if not content_type:
        return False
    return "application/json" in content_type.lower()
