"""Lightweight reranking utilities for retrieval results."""
from __future__ import annotations

import re
from typing import List, Sequence, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing aid only
    from .retrieval import RetrievedChunk


def rerank(query: str, results: Sequence["RetrievedChunk"]) -> List["RetrievedChunk"]:
    """Sort results using a simple lexical overlap heuristic."""

    terms = {
        token.lower()
        for token in re.findall(r"\w+", query)
        if token and token.lower() not in {"the", "a", "an"}
    }
    if not terms:
        return list(results)

    def overlap_score(chunk: "RetrievedChunk") -> tuple[int, float]:
        text = chunk.text.lower()
        matches = sum(1 for term in terms if term in text)
        # Lower ANN score is better; return as secondary key
        return matches, -chunk.score

    sorted_results = sorted(results, key=overlap_score, reverse=True)
    return sorted_results
