"""Chunking utilities."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200
MAX_HEADINGS = 3


@dataclass(slots=True)
class Chunk:
    """Container for a chunk of text and associated metadata."""

    text: str
    start: int
    end: int
    headings: list[str]


def chunk_text(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[Chunk]:
    """Split a block of text using a sliding window strategy."""

    cleaned = _normalize_text(text)
    if not cleaned:
        return []

    headings = _extract_heading_positions(cleaned)
    results: list[Chunk] = []

    start = 0
    length = len(cleaned)
    while start < length:
        end = min(start + chunk_size, length)
        segment = cleaned[start:end].strip()
        if segment:
            results.append(
                Chunk(
                    text=segment,
                    start=start,
                    end=end,
                    headings=_headings_for_position(headings, start),
                )
            )
        if end >= length:
            break
        start = max(end - overlap, start + 1)

    return results


def chunk(documents: Iterable[str]) -> List[str]:
    """Preserve backwards compatibility with the previous chunk API."""

    combined: list[str] = []
    for document in documents:
        combined.extend(chunk_text(document))
    return [item.text for item in combined]


def _normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_heading_positions(text: str) -> list[tuple[int, str]]:
    headings: list[tuple[int, str]] = []
    position = 0
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if _looks_like_heading(line):
            headings.append((position, line))
        position += len(raw_line) + 1
    return headings


_HEADING_NUMBER = re.compile(r"^\s*\d+(?:[.\)])?\s+")


def _looks_like_heading(line: str) -> bool:
    if not line or len(line) > 120:
        return False
    if line.startswith("#"):
        return True
    if line.isupper() and any(c.isalpha() for c in line):
        return True
    if line.endswith(":"):
        return True
    if _HEADING_NUMBER.match(line):
        return True
    return False


def _headings_for_position(headings: list[tuple[int, str]], position: int) -> list[str]:
    relevant = [title for offset, title in headings if offset <= position]
    if len(relevant) <= MAX_HEADINGS:
        return relevant
    return relevant[-MAX_HEADINGS:]
