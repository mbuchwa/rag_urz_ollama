"""Simple rate limiting middleware compatible with FastAPI."""
from __future__ import annotations

from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match

from .errors import RateLimitExceeded


class SlowAPIMiddleware(BaseHTTPMiddleware):
    """Intercept requests and apply registered limiter policies."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        limiter = getattr(request.app.state, "limiter", None)
        route = request.scope.get("route")
        if route is None and hasattr(request.app, "router"):
            for candidate in getattr(request.app.router, "routes", []):
                try:
                    match, _ = candidate.matches(request.scope)
                except Exception:  # pragma: no cover - defensive against non-http routes
                    continue
                if match != Match.NONE:
                    route = candidate
                    break
        endpoint = getattr(route, "endpoint", None)
        limit_info = getattr(endpoint, "__rate_limit__", None)

        hit_result = None
        if limiter and limit_info:
            try:
                hit_result = limiter.hit(request, limit_info)
            except RateLimitExceeded as exc:
                raise exc

        response = await call_next(request)

        if hit_result:
            limit, remaining, reset_at = hit_result
            response.headers.setdefault("X-RateLimit-Limit", str(limit))
            response.headers.setdefault("X-RateLimit-Remaining", str(max(remaining, 0)))
            if reset_at is not None:
                response.headers.setdefault("X-RateLimit-Reset", str(int(reset_at)))

        return response
