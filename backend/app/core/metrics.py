"""Prometheus metric helpers."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "rag_requests_total",
    "HTTP requests processed by the API",
    ("method", "path", "status"),
)

REQUEST_LATENCY = Histogram(
    "rag_request_latency_seconds",
    "Latency of HTTP requests processed by the API",
    ("method", "path"),
    buckets=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
)

TASK_RESULTS = Counter(
    "rag_task_results_total",
    "Background worker task outcomes",
    ("task", "status"),
)


def record_request(method: str, path: str, status_code: int, duration: float) -> None:
    """Record counters and histograms for a processed HTTP request."""

    REQUEST_COUNT.labels(method, path, str(status_code)).inc()
    REQUEST_LATENCY.labels(method, path).observe(duration)


def record_task_result(task_name: str, status: str) -> None:
    """Increment the task results counter for the provided status."""

    TASK_RESULTS.labels(task_name, status).inc()


@contextmanager
def track_request(method: str, path: str) -> Iterator[float]:
    """Context manager that measures a request duration."""

    start = time.perf_counter()
    try:
        yield start
    finally:
        duration = time.perf_counter() - start
        record_request(method, path, 0, duration)

