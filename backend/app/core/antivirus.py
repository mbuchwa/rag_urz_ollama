"""Simple antivirus integration hooks."""
from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class ScanError(RuntimeError):
    """Raised when a scanner reports an infected object."""


class AntivirusScanner(Protocol):
    """Protocol implemented by antivirus scanners."""

    def scan(
        self,
        *,
        bucket: str,
        object_key: str,
        size: int,
        content_type: str,
    ) -> None:
        """Raise ``ScanError`` if the object should be quarantined."""


class NoopScanner:
    """Default scanner implementation used in development."""

    def scan(
        self,
        *,
        bucket: str,
        object_key: str,
        size: int,
        content_type: str,
    ) -> None:
        logger.debug(
            "Skipping antivirus scan for %s (bucket=%s size=%s content_type=%s)",
            object_key,
            bucket,
            size,
            content_type,
        )


_scanner: AntivirusScanner = NoopScanner()


def set_scanner(scanner: AntivirusScanner) -> None:
    """Override the global scanner instance (useful for testing)."""

    global _scanner
    _scanner = scanner


def get_scanner() -> AntivirusScanner:
    """Return the configured antivirus scanner."""

    return _scanner

