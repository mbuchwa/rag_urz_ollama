"""A tiny in-memory rate limiter mimicking SlowAPI's behaviour."""
from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable, Deque, Dict, Tuple

from starlette.requests import Request

from .errors import RateLimitExceeded

WINDOWS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
}


@dataclass(frozen=True)
class LimitConfig:
    label: str
    count: int
    window: int


class Limiter:
    """Simplified limiter compatible with SlowAPI's decorator API."""

    def __init__(self, *, key_func: Callable[[Request], str]) -> None:
        self.key_func = key_func
        self._buckets: Dict[Tuple[str, str, str], Deque[float]] = defaultdict(deque)

    def limit(self, limit_value: str) -> Callable[[Callable[..., object]], Callable[..., object]]:
        config = _parse_limit(limit_value)

        def decorator(func: Callable[..., object]) -> Callable[..., object]:
            setattr(func, "__rate_limit__", config)
            return func

        return decorator

    def hit(self, request: Request, config: LimitConfig) -> Tuple[int, int, int | None]:
        key = self.key_func(request)
        route = request.scope.get("route")
        route_id = getattr(route, "path", request.url.path)
        bucket_key = (key, route_id, config.label)
        bucket = self._buckets[bucket_key]

        now = time.monotonic()
        cutoff = now - config.window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= config.count:
            retry_after = max(0.0, config.window - (now - bucket[0]))
            raise RateLimitExceeded(config.label, retry_after=retry_after)

        bucket.append(now)
        remaining = config.count - len(bucket)
        reset_at = int(bucket[0] + config.window) if bucket else None
        return config.count, remaining, reset_at


_LIMIT_RE = re.compile(r"^(?P<count>\d+)\s*/\s*(?P<period>second|minute|hour|day)s?$", re.IGNORECASE)


def _parse_limit(value: str) -> LimitConfig:
    match = _LIMIT_RE.match(value.strip())
    if not match:
        raise ValueError(f"Unsupported rate limit expression: {value}")
    count = int(match.group("count"))
    period = match.group("period").lower()
    window = WINDOWS[period]
    return LimitConfig(label=value, count=count, window=window)
