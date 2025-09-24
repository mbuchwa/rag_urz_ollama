"""Asynchronous site crawler that discovers and ingests resources."""
from __future__ import annotations

import asyncio
import io
import logging
import re
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable
from urllib.parse import urljoin, urlparse, urlunparse, urldefrag
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.s3 import get_minio_client
from ..models import CrawlResult, Document
from ..models.documents import DocumentStatus

logger = logging.getLogger(__name__)

HTML_TYPES = {"text/html", "application/xhtml+xml"}
PDF_TYPES = {"application/pdf"}
DOCX_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}
SUPPORTED_TYPES = HTML_TYPES | PDF_TYPES | DOCX_TYPES
FILENAME_CLEANER = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(slots=True)
class CrawlSummary:
    """Simple statistics returned after a crawl completes."""

    total: int = 0
    harvested: int = 0
    failed: int = 0
    blocked: int = 0
    skipped: int = 0


async def run_crawl(
    *,
    session: Session,
    job_id: uuid.UUID,
    namespace_id: uuid.UUID,
    root_url: str,
    max_depth: int,
    ingest_callback: Callable[[str], None],
) -> CrawlSummary:
    """Execute the asynchronous crawl orchestration."""

    crawler = _Crawler(
        session=session,
        job_id=job_id,
        namespace_id=namespace_id,
        root_url=root_url,
        max_depth=max_depth,
        ingest_callback=ingest_callback,
    )
    return await crawler.run()


class _Crawler:
    """Internal helper encapsulating crawl state and logic."""

    def __init__(
        self,
        *,
        session: Session,
        job_id: uuid.UUID,
        namespace_id: uuid.UUID,
        root_url: str,
        max_depth: int,
        ingest_callback: Callable[[str], None],
    ) -> None:
        self.session = session
        self.job_id = job_id
        self.namespace_id = namespace_id
        self.root_url = self._normalize_root(root_url)
        self.max_depth = max_depth
        self.ingest_callback = ingest_callback

        parsed = urlparse(self.root_url)
        self.allowed_host = parsed.netloc.lower()
        self.user_agent = "URZ-RAG-Crawler/1.0"
        self.client: httpx.AsyncClient | None = None
        self.minio_client = get_minio_client()
        self.bucket_ready = False
        self.visited: set[str] = set()
        self.seen: set[str] = set()
        self.robots_cache: dict[str, RobotFileParser | None] = {}
        self.summary = CrawlSummary()
        self.last_request: float = 0.0

    async def run(self) -> CrawlSummary:
        """Crawl the root URL breadth-first up to the configured depth."""

        queue: deque[tuple[str, int]] = deque()
        queue.append((self.root_url, 0))
        self.seen.add(self.root_url)

        timeout = httpx.Timeout(20.0, connect=10.0)
        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/pdf"}

        async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
            self.client = client
            while queue:
                url, depth = queue.popleft()
                if url in self.visited:
                    continue
                self.visited.add(url)

                result = CrawlResult(job_id=self.job_id, url=url, depth=depth)
                self.session.add(result)
                self.session.flush()
                self.summary.total += 1

                if not await self._is_allowed(url):
                    result.mark_status("blocked")
                    self.summary.blocked += 1
                    self.session.commit()
                    continue

                try:
                    response = await self._fetch(url)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("Failed to fetch %s: %s", url, exc)
                    result.mark_status("failed", error=str(exc))
                    self.summary.failed += 1
                    self.session.commit()
                    continue

                if response is None:
                    result.mark_status("failed", error="No response")
                    self.summary.failed += 1
                    self.session.commit()
                    continue

                final_url = str(response.url)
                normalized_final = self._normalize_url(final_url)
                if normalized_final is None:
                    result.mark_status("skipped")
                    self.summary.skipped += 1
                    self.session.commit()
                    continue

                result.url = normalized_final
                if normalized_final not in self.visited:
                    self.visited.add(normalized_final)

                content_type = self._detect_content_type(response, normalized_final)
                result.content_type = content_type

                if content_type not in SUPPORTED_TYPES:
                    result.mark_status("skipped")
                    self.summary.skipped += 1
                    self.session.commit()
                    if content_type in HTML_TYPES and depth < self.max_depth:
                    html_text = response.text
                    links = self._extract_links(html_text, normalized_final)
                    self._enqueue_links(queue, links, depth + 1)
                    continue

                try:
                    document_id = await self._ingest_response(
                        response=response,
                        url=normalized_final,
                        depth=depth,
                        content_type=content_type,
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception("Failed to ingest %s: %s", url, exc)
                    result.mark_status("failed", error=str(exc))
                    self.summary.failed += 1
                    self.session.commit()
                    continue

                result.document_id = document_id
                result.mark_status("harvested")
                self.summary.harvested += 1
                self.session.commit()

                if content_type in HTML_TYPES and depth < self.max_depth:
                    html_text = response.text
                    links = self._extract_links(html_text, normalized_final)
                    self._enqueue_links(queue, links, depth + 1)

        return self.summary

    async def _is_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        parser = self.robots_cache.get(base)
        if parser is None:
            parser = await self._fetch_robots(base)
            self.robots_cache[base] = parser
        if parser is None:
            return True
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception:  # pragma: no cover - defensive
            return True

    async def _fetch_robots(self, base: str) -> RobotFileParser | None:
        if not self.client:
            return None
        robots_url = urljoin(base, "/robots.txt")
        try:
            await self._throttle()
            response = await self.client.get(robots_url)
        except httpx.RequestError:
            return None
        if response.status_code >= 400:
            return None
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        return parser

    async def _fetch(self, url: str) -> httpx.Response | None:
        if not self.client:
            return None
        await self._throttle()
        response = await self.client.get(url)
        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {response.status_code} while fetching {url}", request=response.request, response=response
            )
        return response

    async def _throttle(self) -> None:
        loop = asyncio.get_event_loop()
        now = loop.time()
        elapsed = now - self.last_request
        delay = 0.7 - elapsed
        if delay > 0:
            await asyncio.sleep(delay)
        self.last_request = loop.time()

    def _extract_links(self, html: str, base_url: str) -> Iterable[str]:
        soup = BeautifulSoup(html, "html.parser")
        for element in soup(["script", "style", "noscript", "template"]):
            element.decompose()
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "").strip()
            if not href:
                continue
            normalized = self._normalize_url(urljoin(base_url, href))
            if normalized:
                yield normalized

    def _enqueue_links(self, queue: deque[tuple[str, int]], links: Iterable[str], depth: int) -> None:
        if depth > self.max_depth:
            return
        for link in links:
            if link in self.seen:
                continue
            self.seen.add(link)
            queue.append((link, depth))

    async def _ingest_response(
        self,
        *,
        response: httpx.Response,
        url: str,
        depth: int,
        content_type: str,
    ) -> uuid.UUID:
        await self._ensure_bucket()
        data = response.content
        title = None
        if content_type in HTML_TYPES:
            soup = BeautifulSoup(response.text, "html.parser")
            if soup.title and soup.title.string:
                title = soup.title.string.strip() or None
        filename = self._derive_filename(url, content_type)

        document = Document(
            namespace_id=self.namespace_id,
            uri="",
            title=title,
            content_type=content_type,
            metadata={
                "source_url": url,
                "original_filename": filename,
                "crawl_job_id": str(self.job_id),
                "crawl_depth": depth,
            },
            status=DocumentStatus.UPLOADED.value,
        )
        self.session.add(document)
        self.session.flush()

        object_key = f"crawl/{self.namespace_id}/{document.id}/{filename}"
        await asyncio.to_thread(
            self.minio_client.put_object,
            settings.MINIO_BUCKET,
            object_key,
            io.BytesIO(data),
            len(data),
            content_type=content_type,
        )
        document.uri = object_key
        document.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        self.session.commit()

        self.ingest_callback(str(document.id))
        return document.id

    async def _ensure_bucket(self) -> None:
        if self.bucket_ready:
            return
        exists = await asyncio.to_thread(self.minio_client.bucket_exists, settings.MINIO_BUCKET)
        if not exists:
            await asyncio.to_thread(self.minio_client.make_bucket, settings.MINIO_BUCKET)
        self.bucket_ready = True

    def _detect_content_type(self, response: httpx.Response, url: str) -> str:
        header = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if header:
            return header
        path = urlparse(url).path.lower()
        if path.endswith(".pdf"):
            return "application/pdf"
        if path.endswith(".docx"):
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if path.endswith(".doc"):
            return "application/msword"
        return "text/html"

    def _derive_filename(self, url: str, content_type: str) -> str:
        parsed = urlparse(url)
        name = parsed.path.rsplit("/", 1)[-1]
        base = name or ("index.html" if content_type in HTML_TYPES else "document")
        if "." not in base:
            if content_type in HTML_TYPES:
                base = f"{base}.html"
            elif content_type in PDF_TYPES:
                base = f"{base}.pdf"
            elif content_type in DOCX_TYPES:
                base = f"{base}.docx"
        cleaned = FILENAME_CLEANER.sub("_", base).strip("._")
        if not cleaned:
            if content_type in HTML_TYPES:
                return "document.html"
            if content_type in PDF_TYPES:
                return "document.pdf"
            if content_type in DOCX_TYPES:
                return "document.docx"
            return "document.bin"
        return cleaned

    def _normalize_url(self, url: str) -> str | None:
        try:
            resolved = urljoin(self.root_url, url)
        except Exception:  # pragma: no cover - defensive
            return None
        cleaned, _ = urldefrag(resolved)
        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"}:
            return None
        if parsed.netloc.lower() != self.allowed_host:
            return None
        normalized = parsed._replace(fragment="", params="")
        return urlunparse(normalized)

    def _normalize_root(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("URL must be HTTP or HTTPS")
        normalized = parsed._replace(fragment="", params="")
        if not normalized.path:
            normalized = normalized._replace(path="/")
        return urlunparse(normalized)
