"""HTTP client helpers for interacting with a local Ollama instance."""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, Optional

import httpx

from ..core.config import settings


logger = logging.getLogger(__name__)


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

    async def _stream_from_host(host: str) -> AsyncIterator[Dict[str, Any]]:
        async with httpx.AsyncClient(base_url=host, timeout=settings.OLLAMA_TIMEOUT) as client:
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

    try:
        async for chunk in _stream_from_host(settings.OLLAMA_HOST):
            yield chunk
        return
    except httpx.TransportError as primary_error:
        fallback_host = settings.OLLAMA_FALLBACK_HOST
        should_retry_fallback = fallback_host and fallback_host != settings.OLLAMA_HOST
        if should_retry_fallback:
            logger.warning(
                "Primary Ollama host %s unreachable (%s); retrying with fallback %s",
                settings.OLLAMA_HOST,
                primary_error,
                fallback_host,
            )
            try:
                async for chunk in _stream_from_host(fallback_host):
                    yield chunk
                return
            except httpx.TransportError as fallback_error:
                logger.warning(
                    "Fallback Ollama host %s also failed (%s); raising error.",
                    fallback_host,
                    fallback_error,
                )
                raise fallback_error from primary_error
        raise primary_error


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
