"""Ingestion pipeline orchestration stubs."""
from __future__ import annotations

from . import parsers, chunking, embeddings, loaders, crawler


def run_pipeline(namespace: str) -> None:
    """Placeholder ingestion pipeline linking the major stages."""
    resources = crawler.discover(namespace)
    documents = loaders.load(resources)
    parsed = parsers.parse(documents)
    chunks = chunking.chunk(parsed)
    embeddings.embed(chunks)
