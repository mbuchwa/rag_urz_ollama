"""HTTP client helpers for interacting with a local Ollama instance."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, Optional

import httpx

from ..core.config import settings


async def stream_generate(
    prompt: str,
    *,
    model: str | None = None,
    options: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Stream tokens from Ollama's generate endpoint."""

    payload: Dict[str, Any] = {
        "model": model or settings.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": True,
    }
    if options:
        payload["options"] = options

    async with httpx.AsyncClient(base_url=settings.OLLAMA_HOST, timeout=settings.OLLAMA_TIMEOUT) as client:
        async with client.stream("POST", "/api/generate", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yield data


async def complete(prompt: str, *, model: str | None = None) -> str:
    """Convenience helper returning the full generated text."""

    tokens: list[str] = []
    async for chunk in stream_generate(prompt, model=model):
        token = chunk.get("response") or chunk.get("token")
        if token:
            tokens.append(token)
        if chunk.get("done"):
            break
    return "".join(tokens)
