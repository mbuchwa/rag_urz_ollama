"""Error classes compatible with the SlowAPI public API."""
from __future__ import annotations

from typing import Optional

class RateLimitExceeded(Exception):
    """Exception raised when a rate limit bucket is exhausted."""

    def __init__(self, limit: str, *, retry_after: Optional[float] = None) -> None:
        super().__init__(limit)
        self.detail = limit
        self.retry_after = retry_after
        self.status_code = 429
