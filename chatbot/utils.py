import asyncio
import re
from urllib.parse import urlparse, urlunparse


def normalize_url(url: str, ignore_params: bool = True) -> str:
    """Normalize URLs by stripping query parameters and trailing slashes."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host
    if parsed.port:
        netloc += f":{parsed.port}"
    if ignore_params:
        return f"{parsed.scheme}://{netloc}{parsed.path.rstrip('/')}"
    return f"{parsed.scheme}://{netloc}{parsed.path}{parsed.query}"


def extract_url(node):
    """Extract a source URL from a llama-index node."""
    inner_node = getattr(node, "node", node)
    if hasattr(inner_node, "metadata") and isinstance(inner_node.metadata, dict):
        return inner_node.metadata.get("url") or inner_node.metadata.get("source")
    if hasattr(inner_node, "extra_info") and isinstance(inner_node.extra_info, dict):
        return inner_node.extra_info.get("url") or inner_node.extra_info.get("source")
    return None


def clean_response_text(response_text: str):
    """Return the visible answer and optional <think> text.

    Some DeepSeek responses omit the opening <think> tag but still
    include a closing </think>. We handle both the proper pair and the
    dangling closing tag so that the UI never shows the reasoning in the
    main answer.
    """
    # First try to capture an explicit <think>...</think> block
    think_match = re.search(r"<think>(.*?)</think>", response_text,
                            flags=re.IGNORECASE | re.DOTALL)
    if think_match:
        think_content = think_match.group(1).strip()
        main_content = re.sub(r"<think>.*?</think>", "", response_text,
                              flags=re.IGNORECASE | re.DOTALL).strip()
        return main_content, think_content

    # Fallback: if only a closing tag exists, split on it
    closing_match = re.search(r"(.*?)</think>(.*)", response_text,
                              flags=re.IGNORECASE | re.DOTALL)
    if closing_match:
        think_content = closing_match.group(1).strip()
        main_content = closing_match.group(2).strip()
        return main_content, think_content

    # No think tags found
    return response_text.strip(), ""


def run_async(coro):
    """Run an async coroutine from synchronous code, creating a loop if necessary."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)
