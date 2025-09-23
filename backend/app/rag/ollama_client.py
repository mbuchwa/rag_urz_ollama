"""HTTP client for interacting with Ollama."""
from __future__ import annotations

from typing import Any, Dict

import httpx

from ..core.config import settings


async def generate(prompt: str) -> Dict[str, Any]:
    """Call the Ollama API with a prompt and return the response."""
    async with httpx.AsyncClient(base_url=settings.OLLAMA_HOST) as client:
        response = await client.post("/api/generate", json={"prompt": prompt})
        response.raise_for_status()
        return response.json()
