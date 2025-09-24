"""Minimal Prometheus client implementation for offline environments."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Tuple

CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"


_REGISTRY: List["_MetricBase"] = []


@dataclass
class _MetricChild:
    metric: "_MetricBase"
    labels: Tuple[str, ...]
    value: float = 0.0
    buckets: Dict[float, float] = field(default_factory=dict)
    sum: float = 0.0
    count: float = 0.0

    def inc(self, amount: float = 1.0) -> None:
        self.value += amount

    def observe(self, value: float) -> None:
        self.sum += value
        self.count += 1
        for boundary in self.metric.buckets:
            if value <= boundary:
                self.buckets[boundary] = self.buckets.get(boundary, 0.0) + 1
        # Always track +Inf bucket
        self.buckets[float("inf")] = self.buckets.get(float("inf"), 0.0) + 1

    def samples(self) -> Iterable[Tuple[str, float, Dict[str, str]]]:
        if self.metric.metric_type == "counter":
            yield self.metric.name, self.value, dict(zip(self.metric.labelnames, self.labels))
        elif self.metric.metric_type == "histogram":
            base_labels = dict(zip(self.metric.labelnames, self.labels))
            cumulative = 0.0
            for boundary in self.metric.buckets:
                cumulative += self.buckets.get(boundary, 0.0)
                labels = base_labels | {"le": _format_float(boundary)}
                yield f"{self.metric.name}_bucket", cumulative, labels
            total = self.buckets.get(float("inf"), cumulative)
            yield f"{self.metric.name}_bucket", total, base_labels | {"le": "+Inf"}
            yield f"{self.metric.name}_count", self.count, base_labels
            yield f"{self.metric.name}_sum", self.sum, base_labels


class _MetricBase:
    metric_type: str = "counter"

    def __init__(self, name: str, documentation: str, labelnames: Tuple[str, ...]) -> None:
        self.name = name
        self.documentation = documentation
        self.labelnames = labelnames
        self._children: Dict[Tuple[str, ...], _MetricChild] = {}
        self.buckets: Tuple[float, ...] = ()
        _REGISTRY.append(self)

    def labels(self, *values: str) -> _MetricChild:
        if len(values) != len(self.labelnames):
            raise ValueError("Label value count does not match configured names")
        key = tuple(values)
        child = self._children.get(key)
        if child is None:
            child = _MetricChild(metric=self, labels=key)
            if self.metric_type == "histogram":
                child.buckets = {boundary: 0.0 for boundary in self.buckets}
            self._children[key] = child
        return child

    def collect(self) -> Iterable[Tuple[str, float, Dict[str, str]]]:
        for child in self._children.values():
            yield from child.samples()


class Counter(_MetricBase):
    metric_type = "counter"

    def __init__(self, name: str, documentation: str, labelnames: Tuple[str, ...]) -> None:
        super().__init__(name, documentation, labelnames)


class Histogram(_MetricBase):
    metric_type = "histogram"

    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: Tuple[str, ...],
        buckets: Tuple[float, ...],
    ) -> None:
        super().__init__(name, documentation, labelnames)
        self.buckets = tuple(sorted(buckets))


def generate_latest() -> bytes:
    lines: List[str] = []
    for metric in _REGISTRY:
        lines.append(f"# HELP {metric.name} {metric.documentation}")
        lines.append(f"# TYPE {metric.name} {metric.metric_type}")
        for sample_name, sample_value, labels in metric.collect():
            label_str = ""
            if labels:
                formatted = ",".join(f'{key}="{value}"' for key, value in sorted(labels.items()))
                label_str = f"{{{formatted}}}"
            lines.append(f"{sample_name}{label_str} {_format_float(sample_value)}")
        lines.append("")
    return "\n".join(lines).encode("utf-8")


def _format_float(value: float) -> str:
    if value == float("inf"):
        return "+Inf"
    if value == int(value):
        return str(int(value))
    return f"{value:.6f}"
