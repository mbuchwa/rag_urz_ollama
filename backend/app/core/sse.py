"""Server-sent event helpers for streaming responses."""
from __future__ import annotations

from typing import AsyncGenerator, Iterable

from fastapi.responses import StreamingResponse

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Content-Type": "text/event-stream",
    "Connection": "keep-alive",
}


def format_sse(data: str, event: str | None = None) -> str:
    """Return a properly formatted SSE payload."""
    lines = []
    if event:
        lines.append(f"event: {event}")
    for chunk in data.splitlines() or [""]:
        lines.append(f"data: {chunk}")
    lines.append("\n")
    return "\n".join(lines)


def stream(iterable: Iterable[str] | AsyncGenerator[str, None]) -> StreamingResponse:
    """Create a streaming response for an iterable of SSE payloads."""

    async def iterator() -> AsyncGenerator[bytes, None]:
        if hasattr(iterable, "__aiter__"):
            async for item in iterable:  # type: ignore[union-attr]
                yield item.encode("utf-8")
        else:
            for item in iterable:  # type: ignore[union-attr]
                yield item.encode("utf-8")

    return StreamingResponse(iterator(), headers=SSE_HEADERS)
