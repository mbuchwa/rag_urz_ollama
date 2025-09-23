"""Content loaders."""
from __future__ import annotations

from typing import Iterable, List


def load(resources: Iterable[str]) -> List[str]:
    """Placeholder loader that simply returns resource identifiers."""
    return list(resources)
