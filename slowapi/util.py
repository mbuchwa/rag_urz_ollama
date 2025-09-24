"""Utility helpers mirroring SlowAPI's signatures."""
from __future__ import annotations

from starlette.requests import Request


def get_remote_address(request: Request) -> str:
    """Return the best-effort remote address for the request."""

    if request.client:
        return request.client.host or "anonymous"
    return "anonymous"
