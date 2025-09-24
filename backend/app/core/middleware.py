"""Custom ASGI middleware for authentication and CSRF protection."""
from __future__ import annotations

from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable

from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .metrics import record_request

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


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log structured request summaries and emit metrics."""

    def __init__(self, app: Callable) -> None:
        super().__init__(app)
        self.logger = logging.getLogger("rag.request")

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        method = request.method
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            duration = time.perf_counter() - start
            record_request(method, route_path, status_code, duration)
            self.logger.exception(
                "HTTP %s %s raised an unhandled exception", method, route_path
            )
            raise
        duration = time.perf_counter() - start

        user_id = None
        try:
            user_id = request.session.get("user_id")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover - defensive guard for ASGI scope issues
            user_id = getattr(request.state, "user_id", None)

        self.logger.info(
            "HTTP %s %s status=%s user=%s duration=%.3f",
            method,
            route_path,
            status_code,
            user_id or "anonymous",
            duration,
        )
        record_request(method, route_path, status_code, duration)
        response.headers.setdefault("X-Process-Time", f"{duration:.6f}")
        return response


def _is_json_request(request: Request) -> bool:
    content_type = request.headers.get("content-type")
    if not content_type:
        return False
    return "application/json" in content_type.lower()
